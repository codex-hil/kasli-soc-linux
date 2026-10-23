#!/usr/bin/env python3
"""Characterize RX-only reset after an interrupted frame; no GTX/PCS model."""
import binascii
import json
import argparse
from migen import Module, Signal, Memory, ClockDomain, If
from migen.sim import run_simulation
from liteeth.mac import LiteEthMAC
from liteeth.common import eth_phy_description
from litex.soc.interconnect import stream
from test_sfp_logic import PacketTest, MAC


def trial(prefix_length, reset_rx):
    top = Module()
    for name in ('sys', 'eth_tx', 'eth_rx'):
        setattr(top.clock_domains, 'cd_'+name, ClockDomain(name))
    class PHY(Module):
        dw = 8
        tx_clk_freq = rx_clk_freq = 125e6
        def __init__(self):
            self.sink = stream.Endpoint(eth_phy_description(8))
            self.source = stream.Endpoint(eth_phy_description(8))
            self.inject = Signal(reset=1)
            self.byte = Signal(8)
            self.valid = Signal()
            self.comb += [self.source.valid.eq(self.valid | (~self.inject & self.sink.valid)),
                self.source.data.eq(self.byte), self.source.last.eq(0), self.sink.ready.eq(0)]
            self.comb += If(~self.inject, self.sink.connect(self.source))
    top.submodules.phy = phy = PHY()
    top.submodules.mac = mac = LiteEthMAC(phy, dw=8, with_sys_datapath=True,
        tx_cdc_depth=2048, rx_cdc_depth=2048, with_store_and_forward=True)
    top.submodules.test = dut = PacketTest(mac.crossbar.get_port(0x88b5))
    injected = Signal()
    body = MAC.to_bytes(6, 'big')*2 + b'\x88\xb5' + bytes(n ^ 0xa5 for n in range(64))
    frame = b'\x55'*7+b'\xd5'+body+binascii.crc32(body).to_bytes(4, 'little')
    result = {'prefix_bytes': prefix_length, 'reset_eth_rx': reset_rx, 'frames': []}
    def inject():
        for _ in range(40):
            yield
        for byte in frame[:prefix_length]:
            yield phy.valid.eq(1)
            yield phy.byte.eq(byte)
            yield
            while not (yield phy.source.ready):
                yield
        yield phy.valid.eq(0)
        for _ in range(60):
            yield
        if reset_rx:
            yield top.cd_eth_rx.rst.eq(1)
            for _ in range(16):
                yield
            yield top.cd_eth_rx.rst.eq(0)
        for _ in range(60):
            yield
        yield phy.inject.eq(0)
        yield injected.eq(1)
    def run():
        while not (yield injected):
            yield
        for shot in range(3):
            yield dut.start.storage.eq(1)
            yield dut.start.re.eq(1)
            yield
            yield dut.start.re.eq(0)
            for _ in range(600):
                yield
            result['frames'].append({'tx': (yield dut.tx_frames.status),
                'rx': (yield dut.rx_frames.status), 'errors': (yield dut.errors.status),
                'crc': (yield mac.core.rx_datapath.crc_errors.status),
                'preamble': (yield mac.core.rx_datapath.preamble_errors.status)})
    fragment = top.get_fragment()
    for special in fragment.specials:
        if isinstance(special, Memory):
            for port in special.ports:
                if port.dat_r is None:
                    port.dat_r = Signal(special.width)
    clocks = {'sys': 20, 'eth_rx': 8, 'eth_tx': 8}
    for domain in fragment.clock_domains:
        if domain.name not in clocks:
            clocks[domain.name] = 20 if domain.name.startswith('from') else 8
    run_simulation(fragment, {'sys': run(), 'eth_rx': inject()}, clocks=clocks)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix-bytes', type=int, choices=(0, 12, 40, 89), default=12)
    parser.add_argument('--reset-rx', action='store_true')
    args = parser.parse_args()
    result = trial(args.prefix_bytes, args.reset_rx)
    print(json.dumps(result, indent=2), flush=True)
    if args.prefix_bytes == 0 or (args.prefix_bytes == 12 and args.reset_rx):
        assert [row['rx'] for row in result['frames']] == [1, 2, 3], result
        assert all(row['crc'] == 0 for row in result['frames']), result
    if args.prefix_bytes == 12 and not args.reset_rx:
        assert [row['rx'] for row in result['frames']] == [0, 1, 2], result
        assert [row['crc'] for row in result['frames']] == [1, 1, 1], result
    print('PASS: scenario completed; counters above are observations, not a hardware diagnosis')
