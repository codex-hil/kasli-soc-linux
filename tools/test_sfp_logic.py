#!/usr/bin/env python3
"""Exercise numbered MAC payload CSR control, stalls and error detection."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"gateware"))
from migen import Module, Signal, Memory, ClockDomain
from migen.sim import run_simulation
from liteeth.mac.common import LiteEthMACUserPort
from liteeth.mac import LiteEthMAC
from liteeth.core import LiteEthUDPIPCore
from liteeth.common import eth_phy_description
from litex.soc.interconnect import stream
from zc706_sfp import PacketTest, MAC


def test():
    top = Module()
    port = LiteEthMACUserPort(8)
    top.submodules.test = dut = PacketTest(port)
    def run():
        for shot in range(4):
            yield port.sink.ready.eq(0)
            yield
            yield dut.start.storage.eq(1)
            yield dut.start.re.eq(1)
            yield
            yield dut.start.re.eq(0)
            yield
            transmitted = []
            cycle = 0
            while len(transmitted) < 64:
                ready = cycle % 5 != 0
                yield port.sink.ready.eq(ready)
                yield
                if (yield port.sink.valid) and (yield port.sink.ready):
                    n = len(transmitted)
                    assert (yield port.sink.data) == n ^ 0xa5, (shot, cycle, n, (yield port.sink.data))
                    assert (yield port.sink.first) == (n == 0)
                    assert (yield port.sink.last) == (n == 63)
                    assert (yield port.sink.target_mac) == MAC
                    assert (yield port.sink.ethernet_type) == 0x88b5
                    transmitted.append(n)
                cycle += 1
                assert cycle < 150
            yield
            assert (yield dut.tx_frames.status) == shot+1
            assert (yield dut.busy.status) == 0
            length = 63 if shot == 2 else 64
            for n in range(length):
                yield port.source.valid.eq(1)
                yield port.source.data.eq((n ^ 0xa5) ^ (shot == 1 and n == 17))
                yield port.source.error.eq(shot == 3 and n == 63)
                yield port.source.last.eq(n == length-1)
                yield
            yield port.source.valid.eq(0)
            yield
            assert (yield dut.rx_frames.status) == shot+1
            assert (yield dut.errors.status) == shot
    run_simulation(top, run())
    print("PASS: 64-byte numbered MAC payload, TX stalls, repeated CSR triggers, corrupt data, short frame and RX error")


def test_mac_loopback(full_core=False):
    # PHY byte loopback models MAC/CRC and asynchronous system/PHY FIFOs;
    # it does not model the analog GTX or the PCS symbol layer.
    class PHY(Module):
        dw = 8
        tx_clk_freq = rx_clk_freq = 125e6
        def __init__(self):
            self.sink = stream.Endpoint(eth_phy_description(8))
            self.source = stream.Endpoint(eth_phy_description(8))
            self.comb += self.sink.connect(self.source)
    top = Module()
    for name in ("sys", "eth_tx", "eth_rx"):
        setattr(top.clock_domains, "cd_"+name, ClockDomain(name))
    top.submodules.phy = phy = PHY()
    if full_core:
        top.submodules.ethcore = ethcore = LiteEthUDPIPCore(phy, MAC,
            "192.168.2.206", 50e6, dw=8, with_sys_datapath=True,
            icmp_fifo_depth=1536, tx_cdc_depth=2048, rx_cdc_depth=2048,
            with_store_and_forward=True)
        mac = ethcore.mac
        # Match the production crossbar's extra UDP consumer/echo connection.
        from liteeth.common import eth_udp_user_description
        udp = ethcore.udp.crossbar.get_port(1234)
        top.submodules.echo_fifo = echo_fifo = stream.SyncFIFO(
            eth_udp_user_description(8), 2048, buffered=True)
        top.comb += [udp.source.connect(echo_fifo.sink),
            echo_fifo.source.connect(udp.sink, omit={"src_port", "dst_port"}),
            udp.sink.src_port.eq(echo_fifo.source.dst_port),
            udp.sink.dst_port.eq(echo_fifo.source.src_port)]
    else:
        top.submodules.mac = mac = LiteEthMAC(phy, dw=8, with_sys_datapath=True,
            tx_cdc_depth=512, rx_cdc_depth=512, with_store_and_forward=True)
    top.submodules.test = dut = PacketTest(mac.crossbar.get_port(0x88b5))
    def run():
        for shot in range(3):
            yield dut.start.storage.eq(1)
            yield dut.start.re.eq(1)
            yield
            yield dut.start.re.eq(0)
            for _ in range(4000):
                if (yield dut.rx_frames.status) == shot+1:
                    break
                yield
            else:
                raise AssertionError("MAC/CRC/CDC loopback timeout")
            yield
            assert (yield dut.errors.status) == 0
            assert (yield mac.core.rx_datapath.crc_errors.status) == 0
            assert (yield mac.core.rx_datapath.preamble_errors.status) == 0
    fragment = top.get_fragment()
    for special in fragment.specials:
        if isinstance(special, Memory):
            for port in special.ports:
                if port.dat_r is None:
                    port.dat_r = Signal(special.width)
    clocks = {"sys": 20, "eth_tx": 8, "eth_rx": 8}
    for domain in fragment.clock_domains:
        if domain.name not in clocks:
            # ClockDomainCrossing emits local clock-domain aliases.
            clocks[domain.name] = 20 if domain.name.startswith("from") else 8
    run_simulation(fragment, run(), clocks=clocks)
    print("PASS: " + ("full UDP/IP core with ARP/ICMP/UDP echo and test EtherType" if full_core else "MAC") + " loopback with 50 MHz system and 125 MHz PHY clocks")


if __name__ == "__main__":
    test()
    test_mac_loopback()
    test_mac_loopback(full_core=True)
