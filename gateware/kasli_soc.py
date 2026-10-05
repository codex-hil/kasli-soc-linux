#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Minimal Kasli-SoC PS7/GP0/CSR design; PS initialization belongs to SZL."""
import argparse
from pathlib import Path
from migen import ClockDomain, ClockSignal, ResetSignal, Signal
from litex.gen import LiteXModule
from litex.build.generic_platform import Pins, IOStandard
from litex.build.xilinx import XilinxPlatform
from litex.soc.integration.soc_core import SoCCore
from litex.soc.integration.export import get_csr_json
from litex.soc.integration.soc import SoCRegion
from litex.soc.interconnect.csr import CSRStorage, CSRStatus


class Platform(XilinxPlatform):
    def __init__(self):
        # Exact part and LED constraints from Migen sinara/kasli_soc.py.
        super().__init__("xc7z030ffg676-3", [
            ("user_led", 0, Pins("AF19"), IOStandard("LVCMOS25")),
        ], toolchain="openxc7")


class Probe(LiteXModule):
    def __init__(self, led):
        self.scratch = CSRStorage(32, name="scratch")
        self.counter = CSRStatus(32, name="counter")
        self.signature = CSRStatus(32, reset=0x4b534f43, name="signature")
        count = Signal(32)
        self.sync += count.eq(count + 1)
        self.comb += [self.counter.status.eq(count), led.eq(count[25])]


class CRG(LiteXModule):
    def __init__(self):
        self.cd_sys = ClockDomain("sys")
        self.comb += [ClockSignal("sys").eq(ClockSignal("ps7")),
                      ResetSignal("sys").eq(ResetSignal("ps7"))]


class BaseSoC(SoCCore):
    def __init__(self):
        platform = Platform()
        self.crg = CRG()
        super().__init__(platform, 100e6, cpu_type="zynq7000",
                         integrated_rom_size=0, integrated_sram_size=0,
                         with_uart=False, with_timer=False, with_ctrl=False,
                         csr_data_width=32, ident="Kasli-SoC Linux openXC7 probe")
        self.probe = Probe(platform.request("user_led"))
        self.bus.add_region("rom", SoCRegion(origin=self.cpu.reset_address,
                            size=0x10000, mode="r", linker=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--output-dir", default="build/gateware")
    args = parser.parse_args()
    soc = BaseSoC()
    soc.finalize()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "csr.json").write_text(get_csr_json(
        csr_regions=soc.csr_regions, constants=soc.constants,
        mem_regions=soc.mem_regions))
    soc.platform.build(soc, build_dir=str(output / "gateware"), run=args.build)


if __name__ == "__main__":
    main()
