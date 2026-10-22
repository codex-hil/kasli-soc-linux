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
from zc706_sfp import PacketTest, MAC, MACFrameSnapshot, add_crc_captures
from phy_frame_capture import PHYFrameCapture


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


def test_snapshot():
    top = Module()
    port = LiteEthMACUserPort(8)
    top.submodules.snapshot = dut = MACFrameSnapshot(port.source)
    def run():
        yield port.source.ready.eq(1)
        for shot in range(2):
            yield dut.arm.storage.eq(1)
            yield dut.arm.re.eq(1)
            yield
            yield dut.arm.re.eq(0)
            yield port.source.valid.eq(1)
            yield port.source.first.eq(0)  # Ignore an in-flight fragment.
            yield port.source.last.eq(1)
            yield
            yield port.source.valid.eq(0)
            yield
            assert (yield dut.valid.status) == 0
            for n in range(4):
                yield port.source.valid.eq(1)
                yield port.source.first.eq(n == 0)
                yield port.source.last.eq(n == 3)
                yield port.source.ethernet_type.eq(0x88b5 + shot)
                yield port.source.target_mac.eq(MAC)
                yield port.source.sender_mac.eq(MAC + 1)
                yield port.source.error.eq(n == 1 and shot == 1)
                yield
            yield port.source.valid.eq(0)
            yield
            assert (yield dut.valid.status) == 1
            assert (yield dut.payload_bytes.status) == 4
            assert (yield dut.ethernet_type.status) == 0x88b5 + shot
            assert (yield dut.error.status) == shot
            assert (yield dut.target_lo.status) == MAC & 0xffffffff
            assert (yield dut.sender_hi.status) == (MAC + 1) >> 32
            yield port.source.valid.eq(1)
            yield port.source.first.eq(1)
            yield port.source.last.eq(1)
            yield port.source.ethernet_type.eq(0)
            yield
            yield port.source.valid.eq(0)
            yield
            assert (yield dut.ethernet_type.status) == 0x88b5 + shot
    run_simulation(top, run())
    print("PASS: passive frame snapshot rearm, fragment rejection, length, errors and freeze")


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
    if full_core:
        top.submodules.tx_capture = tx_capture = MACFrameSnapshot(mac.packetizer.sink)
        top.submodules.rx_capture = rx_capture = MACFrameSnapshot(mac.depacketizer.source)
        top.submodules.tx_raw = tx_raw = PHYFrameCapture(phy.sink, 'eth_tx')
        top.submodules.rx_raw = rx_raw = PHYFrameCapture(phy.source, 'eth_rx')
        add_crc_captures(top, mac)
        crc_captures = (top.rx_cdc_raw, top.crc_input_raw, top.crc_output_raw)
    def run():
        for shot in range(3):
            if full_core:
                for capture in (tx_capture, rx_capture, tx_raw, rx_raw) + crc_captures:
                    yield capture.arm.storage.eq(1)
                    yield capture.arm.re.eq(1)
                yield
                for capture in (tx_capture, rx_capture, tx_raw, rx_raw) + crc_captures:
                    yield capture.arm.re.eq(0)
                yield
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
            if full_core:
                for capture in (tx_capture, rx_capture):
                    assert (yield capture.valid.status) == 1
                    assert (yield capture.ethernet_type.status) == 0x88b5
                    assert (yield capture.payload_bytes.status) == 64
                    assert (yield capture.error.status) == 0
                raw_frames = []
                for raw in (tx_raw, rx_raw):
                    assert (yield raw.done.status) == 1
                    assert (yield raw.length.status) == 90
                    assert (yield raw.overflow.status) == 0
                    assert (yield raw.error.status) == 0
                    data = []
                    for address in range(90):
                        yield raw.address.storage.eq(address)
                        yield
                        data.append((yield raw.data.status))
                    raw_frames.append(bytes(data))
                assert raw_frames[0] == raw_frames[1]
                assert raw_frames[0][:8] == b'\x55'*7 + b'\xd5'
                import binascii
                expected = binascii.crc32(raw_frames[0][8:-4]).to_bytes(4, 'little')
                assert raw_frames[0][-4:] == expected
                for capture, expected_data in zip(crc_captures,
                        (raw_frames[0], raw_frames[0][8:], raw_frames[0][8:-4])):
                    assert (yield capture.done.status) == 1
                    assert (yield capture.length.status) == len(expected_data)
                    assert (yield capture.overflow.status) == 0
                    assert (yield capture.error.status) == 0
                    captured = []
                    for address in range(len(expected_data)):
                        yield capture.address.storage.eq(address)
                        yield
                        captured.append((yield capture.data.status))
                    assert bytes(captured) == expected_data
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
    test_snapshot()
    test()
    test_mac_loopback()
    test_mac_loopback(full_core=True)
