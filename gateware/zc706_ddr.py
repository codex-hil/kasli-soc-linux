#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent ZC706 PL SODIMM bring-up: upstream LiteDRAM, PS GP1, native BIST."""
import argparse
import json
from pathlib import Path
from migen import ClockDomain, ClockSignal, ResetSignal, Signal, Instance
from litex.gen import LiteXModule
from litex.soc.cores.clock import S7MMCM, S7IDELAYCTRL
from litex.soc.interconnect.csr import CSRStatus
from litex.soc.interconnect import wishbone, axi
from litex.soc.integration.soc import SoCRegion
from litedram.frontend.wishbone import LiteDRAMWishbone2Native
from litex.soc.integration.export import get_csr_json, get_csr_header, get_mem_header, get_soc_header
from litex_boards.platforms.xilinx_zc706 import _io
from litedram.modules import MT8JTF12864
from litedram.phy.s7ddrphy import K7DDRPHY
from litedram.init import get_sdram_phy_c_header
from kasli_soc import BaseSoC

ROOT = Path(__file__).resolve().parents[1]


class DDRClock(LiteXModule):
    def __init__(self):
        self.cd_sys = ClockDomain("sys")
        self.cd_sys4x = ClockDomain("sys4x")
        self.cd_idelay = ClockDomain("idelay")
        self.mmcm = S7MMCM(speedgrade=-2, fractional=False)
        self.comb += self.mmcm.reset.eq(ResetSignal("ps7"))
        self.mmcm.register_clkin(ClockSignal("ps7"), 100e6)
        # CLK and CLKDIV must come from the same MMCM with matching BUFGs.
        self.mmcm.create_clkout(self.cd_sys, 100e6)
        self.mmcm.create_clkout(self.cd_sys4x, 400e6)
        self.mmcm.create_clkout(self.cd_idelay, 200e6)
        self.idelayctrl = S7IDELAYCTRL(self.cd_idelay)
        self.ready = Signal()
        for special in self.idelayctrl._fragment.specials:
            if isinstance(special, Instance) and special.of == "IDELAYCTRL":
                special.items.append(Instance.Output("RDY", self.ready))
        # nextpnr duplicates this into every used bank and ANDs all RDY outputs.


class DDRStatus(LiteXModule):
    def __init__(self, crg):
        from migen import Cat
        from migen.genlib.cdc import MultiReg
        self.signature = CSRStatus(32, reset=0x504c4444, name="signature")
        self.ready = CSRStatus(2, name="ready")
        calibrated = Signal()
        self.specials += MultiReg(crg.ready, calibrated)
        self.comb += self.ready.status.eq(Cat(crg.mmcm.locked, calibrated))


class DDRSoC(BaseSoC):
    def __init__(self):
        super().__init__("zc706", crg=DDRClock())
        self.csr.add("probe", 1)
        self.csr.add("ddrphy", 2)
        self.csr.add("sdram", 3)
        self.csr.add("sdram_generator", 4)
        self.csr.add("sdram_checker", 5)
        self.csr.add("ddr_status", 6)
        # The complete 1 GiB PL RAM occupies GP1, leaving GP0 for CSRs.
        gp1 = self.cpu.add_axi_gp_master()
        for port in (0, 1):
            self.cpu.cpu_params[f"i_M_AXI_GP{port}_ACLK"] = ClockSignal("sys")
        # Reuse the upstream board resource verbatim, including SSTL/DCI standards.
        self.platform.add_extension([resource for resource in _io if resource[0] == "ddram"])
        self.ddrphy = K7DDRPHY(self.platform.request("ddram"), memtype="DDR3",
            nphases=4, sys_clk_freq=100e6, iodelay_clk_freq=200e6)
        self.dram_module = MT8JTF12864(100e6, "1:4")
        self.add_sdram("sdram", phy=self.ddrphy, module=self.dram_module,
            with_soc_interconnect=False, with_bist=True)
        # Zynq treats all PL addresses as IO; expose this diagnostic memory
        # uncached, using the same upstream bridge without a CPU/L2 cache.
        ram_bus = wishbone.Interface(data_width=32, address_width=32)
        # Match LiteX's normal SDRAM frontend: let the Wishbone adapter select
        # a 32-bit lane in the native 512-bit word. A separate generic native
        # converter creates an unnecessary ordered-command FIFO and long
        # ready/valid feedback path (75.99 MHz in the rejected build).
        port = self.sdram.crossbar.get_port()
        self.ram_bridge = LiteDRAMWishbone2Native(ram_bus, port, base_address=0x80000000)
        # PS decodes GP0 and GP1 into disjoint windows already. A shared
        # AXI-Lite crossbar adds a long round-trip through unrelated slaves.
        self.ps_ram_bridge = axi.AXI2Wishbone(gp1, ram_bus)
        self.bus.add_region("main_ram",
            SoCRegion(origin=0x80000000, size=0x40000000, cached=False))
        self.ddr_status = DDRStatus(self.crg)
        self.add_constant("PL_DDR_ABI", 1)
        self.add_constant("PL_DDR_SIZE", 0x40000000)
        for clk, period in ((self.crg.cd_sys.clk, 10), (self.crg.cd_sys4x.clk, 2.5),
                            (self.crg.cd_idelay.clk, 5)):
            self.platform.add_period_constraint(clk, period)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--board", choices=["zc706"], default="zc706")
    p.add_argument("--output-dir", default="build/zc706-ddr/gateware")
    args = p.parse_args()
    soc = DDRSoC()
    soc.finalize()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output/'csr.json').write_text(get_csr_json(csr_regions=soc.csr_regions, constants=soc.constants, mem_regions=soc.mem_regions))
    generated = output/'include/generated'
    generated.mkdir(parents=True, exist_ok=True)
    (generated/'csr.h').write_text(get_csr_header(soc.csr_regions, soc.constants))
    (generated/'mem.h').write_text(get_mem_header(soc.mem_regions))
    (generated/'soc.h').write_text(get_soc_header(soc.constants))
    (generated/'sdram_phy.h').write_text(get_sdram_phy_c_header(soc.ddrphy.settings,
        soc.dram_module.timing_settings, soc.dram_module.geom_settings))
    soc.platform.build(soc, build_dir=str(output/'gateware'), run=False)


if __name__ == '__main__':
    main()
