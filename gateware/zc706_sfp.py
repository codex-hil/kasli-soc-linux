#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Isolated ZC706 SFP: upstream GTX BASE-X, MAC/ARP/ICMP/UDP and CSR diagnostics."""
import argparse
from pathlib import Path
from migen import Signal, Instance, Cat, If, Constant, ClockDomain, ClockSignal, ResetSignal
from migen.genlib.cdc import MultiReg
from litex.gen import LiteXModule
from litex.build.generic_platform import Pins, Subsignal
from litex.soc.cores.bitbang import I2CMaster
from litex.soc.cores.clock import S7MMCM
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import CSRStorage, CSRStatus
from litex.soc.integration.export import get_csr_json
from litex_boards.platforms.xilinx_zc706 import _io
from liteeth.phy import K7_1000BASEX
from liteeth.core import LiteEthUDPIPCore
from liteeth.common import eth_udp_user_description
from kasli_soc import BaseSoC

MAC = 0x02c0de706001


class ZC706PHY(K7_1000BASEX):
    # These frequencies support a 2.5 GHz CPLL / OUT_DIV=4.
    supported_refclk_freqs = (100e6, 125e6, 156.25e6, 200e6)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # nextpnr does not yet constrain regional BUFH consumers to the
        # region. Use global BUFGs for the three TX clocks, matching the
        # upstream RX clocking. Clock rates, MMCM ratios and resets stay intact.
        changed = 0
        for module in (self.pma, self.tx_mmcm):
            for special in module._fragment.specials:
                if isinstance(special, Instance) and special.of == "BUFH":
                    special.of = "BUFG"
                    changed += 1
        if changed != 3:
            raise RuntimeError("Upstream TX clock-buffer structure changed")


class PacketTest(LiteXModule):
    """64-byte numbered payload through the complete MAC/PCS/GTX RX path."""
    def __init__(self, port):
        self.start = CSRStorage(1, name="start")
        self.busy = CSRStatus(1, name="busy")
        self.tx_frames = CSRStatus(32, name="tx_frames")
        self.rx_frames = CSRStatus(32, name="rx_frames")
        self.errors = CSRStatus(32, name="errors")
        index = Signal(6)
        rx_index = Signal(7)
        bad = Signal()
        self.comb += [port.sink.valid.eq(self.busy.status),
            port.sink.first.eq(index == 0), port.sink.last.eq(index == 63),
            port.sink.data.eq(index ^ 0xa5), port.sink.be.eq(1),
            port.sink.error.eq(0), port.sink.target_mac.eq(MAC),
            port.sink.sender_mac.eq(MAC), port.sink.ethernet_type.eq(0x88b5),
            port.source.ready.eq(1)]
        mismatch = (port.source.data != (rx_index ^ 0xa5)) | port.source.error
        self.sync += [
            If(self.start.re & self.start.storage & ~self.busy.status,
                self.busy.status.eq(1), index.eq(0)),
            If(port.sink.valid & port.sink.ready,
                If(port.sink.last, self.busy.status.eq(0),
                    self.tx_frames.status.eq(self.tx_frames.status + 1))
                .Else(index.eq(index + 1))),
            If(port.source.valid & port.source.ready,
                bad.eq(bad | mismatch), rx_index.eq(rx_index + 1),
                If(port.source.last,
                    self.rx_frames.status.eq(self.rx_frames.status + 1),
                    If(bad | mismatch | (rx_index != 63),
                        self.errors.status.eq(self.errors.status + 1)),
                    bad.eq(0), rx_index.eq(0)))
        ]


class Diagnostics(LiteXModule):
    def __init__(self, phy, si5324, tx_enable, fabric_refclk=False, local_refclk=False):
        self.control = CSRStorage(5, reset=8, name="control")
        self.status = CSRStatus(8, name="status")
        self.signature = CSRStatus(32, reset=0x53465031, name="signature")
        self.rx_count = CSRStatus(32, name="rx_count")
        self.tx_count = CSRStatus(32, name="tx_count")
        self.si_ref_count = CSRStatus(32, name="si_ref_count")
        self.gt_ref_count = CSRStatus(32, name="gt_ref_count")
        self.clock_faults = CSRStatus(3, name="clock_faults")
        self.drp_address = CSRStorage(9, name="drp_address")
        self.drp_write_data = CSRStorage(16, name="drp_write_data")
        self.drp_command = CSRStorage(2, name="drp_command")
        self.drp_read_data = CSRStatus(16, name="drp_read_data")
        self.drp_busy = CSRStatus(1, name="drp_busy")
        drp_en = Signal(); drp_we = Signal(); drp_ready = Signal(); drp_data = Signal(16)
        self.sync += [drp_en.eq(0),
            If(self.drp_command.re & ~self.drp_busy.status,
               drp_en.eq(1), drp_we.eq(self.drp_command.storage[0]), self.drp_busy.status.eq(1)),
            If(drp_ready, self.drp_read_data.status.eq(drp_data), self.drp_busy.status.eq(0))]
        self.cd_si_ref = ClockDomain("si_ref", reset_less=True)
        self.cd_gt_ref = ClockDomain("gt_ref", reset_less=True)
        si_div2 = Signal(); gt_ref = Signal()
        ref_lost = Signal(); feedback_lost = Signal()
        self.specials += [Instance("BUFG", i_I=si_div2, o_O=self.cd_si_ref.clk),
                          Instance("BUFG", i_I=gt_ref, o_O=self.cd_gt_ref.clk)]
        buffers = [s for s in phy.pma._fragment.specials
                   if isinstance(s, Instance) and s.of == "IBUFDS_GTE2"]
        if len(buffers) != 1:
            raise RuntimeError("Expected a dedicated GTX reference buffer")
        buffers[0].items.append(Instance.Output("ODIV2", si_div2))
        self.specials += MultiReg(Cat(ref_lost, feedback_lost, phy.pll.reset),
                                  self.clock_faults.status)
        # 0:2 loopback, 3 Si5324 reset_n, 4 PHY reset. TX enable_n is inverted
        # by the board's discrete transistor (same polarity as upstream target).
        loop = Signal(3)
        self.specials += MultiReg(self.control.storage[:3], loop, "eth_tx_half")
        self.comb += [si5324.rst_n.eq(self.control.storage[3]), tx_enable.eq(1),
                      phy.reset.eq(self.control.storage[4])]
        instances = [s for s in phy.pma._fragment.specials
                     if isinstance(s, Instance) and s.of == "GTXE2_CHANNEL"]
        if len(instances) != 1:
            raise RuntimeError("Expected upstream PMA's single GTX channel")
        for item in instances[0].items:
            if isinstance(item, Instance.Output):
                if item.name == "CPLLREFCLKLOST":
                    item.expr = ref_lost
                elif item.name == "CPLLFBCLKLOST":
                    item.expr = feedback_lost
                elif item.name == "GTREFCLKMONITOR":
                    item.expr = gt_ref
                elif item.name == "DRPDO":
                    item.expr = drp_data
                elif item.name == "DRPRDY":
                    item.expr = drp_ready
            if isinstance(item, Instance.Input):
                drp_inputs = {"DRPCLK": ClockSignal("sys"), "DRPADDR": self.drp_address.storage,
                              "DRPDI": self.drp_write_data.storage, "DRPEN": drp_en, "DRPWE": drp_we}
                if item.name in drp_inputs:
                    item.expr = drp_inputs[item.name]
            if isinstance(item, Instance.Input) and item.name == "LOOPBACK":
                item.expr = loop
            # Si5324 feeds REFCLK1 of quad 110 below SFP quad 111.
            # UG476: clocks from the quad below enter GTNORTHREFCLK*.
            elif isinstance(item, Instance.Input) and item.name == "GTREFCLK0":
                item.expr = Constant(0)
            elif isinstance(item, Instance.Input) and item.name == "GTNORTHREFCLK1":
                item.expr = Constant(0) if local_refclk else phy.pll.refclk
            elif isinstance(item, Instance.Input) and item.name == "GTREFCLK1":
                item.expr = phy.pll.refclk if local_refclk else Constant(0)
            elif isinstance(item, Instance.Input) and item.name == "GTGREFCLK":
                item.expr = ClockSignal("ps7") if fabric_refclk else Constant(0)
            elif isinstance(item, Instance.Input) and item.name == "CPLLREFCLKSEL":
                item.expr = Constant(0b111 if fabric_refclk else (0b010 if local_refclk else 0b100), 3)
        flags = Cat(phy.pll.lock, phy.tx_init.done, phy.rx_init.done,
            phy.tx_mmcm.locked, phy.rx_mmcm.locked, phy.link_up,
            si5324.int_n, phy.pcs.is_sgmii)
        self.specials += MultiReg(flags, self.status.status)
        # Gray counters permit frequency measurement without incoherent binary CDC.
        for domain, csr in [("eth_tx", self.tx_count), ("eth_rx", self.rx_count),
                            ("si_ref", self.si_ref_count), ("gt_ref", self.gt_ref_count)]:
            count = Signal(32); gray = Signal(32)
            getattr(self.sync, domain).__iadd__([count.eq(count + 1),
                gray.eq((count + 1) ^ ((count + 1) >> 1))])
            self.specials += MultiReg(gray, csr.status)


class SFPClock(LiteXModule):
    def __init__(self):
        self.cd_sys = ClockDomain("sys")
        self.mmcm = S7MMCM(speedgrade=-2, fractional=False)
        self.mmcm.register_clkin(ClockSignal("ps7"), 100e6)
        self.mmcm.create_clkout(self.cd_sys, 50e6)
        self.comb += self.mmcm.reset.eq(ResetSignal("ps7"))


class SFPSoC(BaseSoC):
    def __init__(self, ip="192.168.2.206", refclk="si5324"):
        super().__init__("zc706", crg=SFPClock(), sys_clk_freq=50e6)
        # The AXI master and GP0 frontend run in sys, not the 100 MHz FCLK.
        self.cpu.cpu_params["i_M_AXI_GP0_ACLK"] = ClockSignal("sys")
        self.csr.add("probe", 1)
        self.platform.add_extension([r for r in _io if r[0] in
            ("sfp", "sfp_tx_disable_n", "mgt_refclk", "si5324", "i2c")])
        self.board_i2c = I2CMaster(self.platform.request("i2c"))
        self.csr.add("board_i2c", 2)
        if refclk == "local":
            # Unused HPC DP4 in the Si5324 quad; no external FMC traffic.
            self.platform.add_extension([("gtx_local", 0,
                Subsignal("txp", Pins("AH2")), Subsignal("txn", Pins("AH1")),
                Subsignal("rxp", Pins("AH6")), Subsignal("rxn", Pins("AH5")))])
        self.ethphy = ZC706PHY(self.platform.request("mgt_refclk"),
            self.platform.request("gtx_local" if refclk == "local" else "sfp"), 50e6, refclk_freq=100e6 if refclk == "fclk" else 125e6, with_csr=False)
        self.sfp_status = Diagnostics(self.ethphy, self.platform.request("si5324"),
            self.platform.request("sfp_tx_disable_n"), fabric_refclk=refclk == "fclk", local_refclk=refclk == "local")
        self.csr.add("sfp_status", 3)
        self.ethcore = LiteEthUDPIPCore(self.ethphy, MAC, ip, 50e6,
            dw=8, with_sys_datapath=True, icmp_fifo_depth=1536,
            tx_cdc_depth=2048, rx_cdc_depth=2048, with_store_and_forward=True)
        self.mac_status = LiteXModule()
        for name in ("crc_errors", "preamble_errors"):
            csr = CSRStatus(32, name=name)
            setattr(self.mac_status, name, csr)
            self.comb += csr.status.eq(getattr(self.ethcore.mac.core.rx_datapath, name).status)
        for name, endpoint in [("tx_frames", self.ethcore.mac.core.sink),
                               ("rx_frames", self.ethcore.mac.core.source)]:
            csr = CSRStatus(32, name=name)
            setattr(self.mac_status, name, csr)
            self.sync += If(endpoint.valid & endpoint.ready & endpoint.last,
                csr.status.eq(csr.status + 1))
        self.csr.add("mac_status", 4)
        self.packet_test = PacketTest(self.ethcore.mac.crossbar.get_port(0x88b5))
        self.csr.add("packet_test", 5)
        udp = self.ethcore.udp.crossbar.get_port(1234)
        self.echo_fifo = stream.SyncFIFO(eth_udp_user_description(8), 2048, buffered=True)
        self.comb += [udp.source.connect(self.echo_fifo.sink),
            self.echo_fifo.source.connect(udp.sink, omit={"src_port", "dst_port"}),
            udp.sink.src_port.eq(self.echo_fifo.source.dst_port),
            udp.sink.dst_port.eq(self.echo_fifo.source.src_port)]
        self.add_constant("SFP_ABI", 1)
        self.add_constant("SFP_MAC", MAC)
        self.add_constant("SFP_IP", ip)
        self.add_constant("SFP_REFCLK_HZ", 100000000 if refclk == "fclk" else 125000000)
        self.add_constant("SFP_REFCLK_SOURCE", refclk)
        self.platform.add_period_constraint(self.crg.cd_sys.clk, 20)
        self.platform.add_period_constraint(self.ethphy.cd_eth_tx.clk, 8)
        self.platform.add_period_constraint(self.ethphy.cd_eth_rx.clk, 8)
        self.platform.add_period_constraint(self.sfp_status.cd_si_ref.clk, 16)
        self.platform.add_period_constraint(self.sfp_status.cd_gt_ref.clk, 10 if refclk == "fclk" else 8)
        self.platform.add_false_path_constraints(self.crg.cd_sys.clk,
            self.sfp_status.cd_si_ref.clk, self.sfp_status.cd_gt_ref.clk)
        self.platform.add_period_constraint(self.ethphy.txoutclk, 16)
        self.platform.add_period_constraint(self.ethphy.rxoutclk, 16)
        self.platform.add_false_path_constraints(self.crg.cd_sys.clk,
            self.ethphy.cd_eth_tx.clk, self.ethphy.cd_eth_rx.clk)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--board", choices=["zc706"], default="zc706")
    p.add_argument("--output-dir", default="build/zc706-sfp/gateware")
    p.add_argument("--refclk", choices=["si5324", "fclk", "local"], default="si5324")
    a = p.parse_args()
    soc = SFPSoC(refclk=a.refclk); soc.finalize()
    out = Path(a.output_dir); out.mkdir(parents=True, exist_ok=True)
    (out/"csr.json").write_text(get_csr_json(csr_regions=soc.csr_regions,
        constants=soc.constants, mem_regions=soc.mem_regions))
    soc.platform.build(soc, build_dir=str(out/"gateware"), run=False)


if __name__ == "__main__":
    main()
