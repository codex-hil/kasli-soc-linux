#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Isolated ZC706 SFP: upstream GTX BASE-X, MAC/ARP/ICMP/UDP and CSR diagnostics."""
import argparse
from pathlib import Path
from migen import Signal, Instance, Cat, If, Constant, ClockDomain, ClockSignal, ResetSignal
from migen.genlib.cdc import MultiReg
from litex.gen import LiteXModule
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
    # All three frequencies give the supported 2.5 GHz CPLL / OUT_DIV=4.
    supported_refclk_freqs = (125e6, 156.25e6, 200e6)

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
    def __init__(self, phy, si5324, tx_enable):
        self.control = CSRStorage(5, reset=8, name="control")
        self.status = CSRStatus(8, name="status")
        self.signature = CSRStatus(32, reset=0x53465031, name="signature")
        self.rx_count = CSRStatus(32, name="rx_count")
        self.tx_count = CSRStatus(32, name="tx_count")
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
            if isinstance(item, Instance.Input) and item.name == "LOOPBACK":
                item.expr = loop
            # Si5324 feeds REFCLK1 of quad 110; SFP is in adjacent quad 111.
            elif isinstance(item, Instance.Input) and item.name == "GTREFCLK0":
                item.expr = Constant(0)
            elif isinstance(item, Instance.Input) and item.name == "GTSOUTHREFCLK1":
                item.expr = phy.pll.refclk
            elif isinstance(item, Instance.Input) and item.name == "CPLLREFCLKSEL":
                item.expr = Constant(0b110, 3)
        flags = Cat(phy.pll.lock, phy.tx_init.done, phy.rx_init.done,
            phy.tx_mmcm.locked, phy.rx_mmcm.locked, phy.link_up,
            si5324.int_n, phy.pcs.is_sgmii)
        self.specials += MultiReg(flags, self.status.status)
        # Gray counters permit frequency measurement without incoherent binary CDC.
        for domain, csr in [("eth_tx", self.tx_count), ("eth_rx", self.rx_count)]:
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
    def __init__(self, ip="192.168.2.206"):
        super().__init__("zc706", crg=SFPClock(), sys_clk_freq=50e6)
        self.csr.add("probe", 1)
        self.platform.add_extension([r for r in _io if r[0] in
            ("sfp", "sfp_tx_disable_n", "mgt_refclk", "si5324", "i2c")])
        self.board_i2c = I2CMaster(self.platform.request("i2c"))
        self.csr.add("board_i2c", 2)
        self.ethphy = ZC706PHY(self.platform.request("mgt_refclk"),
            self.platform.request("sfp"), 50e6, refclk_freq=125e6, with_csr=False)
        self.sfp_status = Diagnostics(self.ethphy, self.platform.request("si5324"),
            self.platform.request("sfp_tx_disable_n"))
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
        self.add_constant("SFP_REFCLK_HZ", 125000000)
        self.platform.add_period_constraint(self.crg.cd_sys.clk, 20)
        self.platform.add_period_constraint(self.ethphy.cd_eth_tx.clk, 8)
        self.platform.add_period_constraint(self.ethphy.cd_eth_rx.clk, 8)
        self.platform.add_period_constraint(self.ethphy.txoutclk, 16)
        self.platform.add_period_constraint(self.ethphy.rxoutclk, 16)
        self.platform.add_false_path_constraints(self.crg.cd_sys.clk,
            self.ethphy.cd_eth_tx.clk, self.ethphy.cd_eth_rx.clk)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--board", choices=["zc706"], default="zc706")
    p.add_argument("--output-dir", default="build/zc706-sfp/gateware")
    a = p.parse_args()
    soc = SFPSoC(); soc.finalize()
    out = Path(a.output_dir); out.mkdir(parents=True, exist_ok=True)
    (out/"csr.json").write_text(get_csr_json(csr_regions=soc.csr_regions,
        constants=soc.constants, mem_regions=soc.mem_regions))
    soc.platform.build(soc, build_dir=str(out/"gateware"), run=False)


if __name__ == "__main__":
    main()
