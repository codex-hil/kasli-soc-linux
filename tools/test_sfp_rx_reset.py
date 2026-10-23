#!/usr/bin/env python3
"""Characterize RX-only reset after an interrupted frame; no GTX/PCS model."""
import binascii
import json
import argparse
from unittest.mock import patch
from migen.genlib.resetsync import AsyncResetSynchronizer
from test_sfp_cdc_reset import IdealReset
from migen import Module, Signal, Memory, ClockDomain, If, ResetInserter, ResetSignal
from migen.sim import run_simulation
from liteeth.mac import LiteEthMAC
from liteeth.common import eth_phy_description
from litex.soc.interconnect import stream
from test_sfp_logic import PacketTest, MAC
from network_reset import NetworkReset


def trial(prefix_length, reset_rx, queued=False, common_cdc=False, reset_mac=False, network_reset=False):
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
            self.last = Signal()
            self.comb += [self.source.valid.eq(self.valid | (~self.inject & self.sink.valid)),
                self.source.data.eq(self.byte), self.source.be.eq(1), self.source.last.eq(self.last), self.sink.ready.eq(0)]
            self.comb += If(~self.inject, self.sink.connect(self.source))
    top.submodules.phy = phy = PHY()
    alias_rates = {}
    original_cdc = stream.ClockDomainCrossing
    def make_cdc(*args, **kwargs):
        if kwargs.get('cd_from') == 'eth_rx' and kwargs.get('cd_to') == 'sys':
            kwargs['with_common_rst'] = common_cdc
        if reset_mac and kwargs.get('cd_from') == 'sys' and kwargs.get('cd_to') == 'eth_tx':
            kwargs['with_common_rst'] = True
        instance = original_cdc(*args, **kwargs)
        if kwargs.get('with_common_rst'):
            alias_rates[f'from{instance.duid}'] = 20 if kwargs['cd_from'] == 'sys' else 8
            alias_rates[f'to{instance.duid}'] = 20 if kwargs['cd_to'] == 'sys' else 8
        return instance
    with patch.object(stream, 'ClockDomainCrossing', make_cdc):
        top.submodules.mac = mac = LiteEthMAC(phy, dw=8, with_sys_datapath=True,
            tx_cdc_depth=2048, rx_cdc_depth=2048, with_store_and_forward=True)
    from liteeth.mac.preamble import LiteEthMACPreambleChecker
    preamble = next(stage for stage in mac.core.rx_datapath.pipeline
        if isinstance(stage, LiteEthMACPreambleChecker))
    seen_sys = Signal(32)
    top.sync += If(preamble.sink.valid & preamble.sink.ready, seen_sys.eq(seen_sys + 1))
    top.submodules.test = dut = PacketTest(mac.crossbar.get_port(0x88b5))
    if reset_mac:
        # Reset the whole MAC sys state and its diagnostic packet consumer.
        # This is a model strategy, not a production integration patch.
        ResetInserter(['sys'])(mac)
        ResetInserter(['sys'])(dut)
        top.comb += [mac.reset_sys.eq(ResetSignal('eth_rx')),
            dut.reset_sys.eq(ResetSignal('eth_rx'))]
    if network_reset:
        top.submodules.recovery = recovery = NetworkReset(ResetSignal('eth_rx'))
        recovery.wrap(mac)
        recovery.wrap(dut)
        alias_rates.update({'net_sys': 20, 'net_eth_tx': 8, 'net_eth_rx': 8})
    injected = Signal()
    body = MAC.to_bytes(6, 'big')*2 + b'\x88\xb5' + bytes(n ^ 0xa5 for n in range(64))
    frame = b'\x55'*7+b'\xd5'+body+binascii.crc32(body).to_bytes(4, 'little')
    result = {'prefix_bytes': prefix_length, 'reset_eth_rx': reset_rx, 'queued_frame': queued, 'common_cdc': common_cdc, 'reset_mac_and_consumer': reset_mac, 'network_reset': network_reset, 'frames': []}
    def inject():
        for _ in range(40):
            yield
        for index, byte in enumerate(frame if queued else frame[:prefix_length]):
            yield phy.valid.eq(1)
            yield phy.byte.eq(byte)
            yield phy.last.eq(queued and index == len(frame)-1)
            yield
            while not (yield phy.source.ready):
                yield
        yield phy.valid.eq(0)
        if queued:
            while (yield seen_sys) < prefix_length:
                yield
            result["sys_bytes_at_reset_request"] = (yield seen_sys)
        else:
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
            clocks[domain.name] = alias_rates.get(domain.name, 8 if domain.name.startswith('from') else 20)
    run_simulation(fragment, {'sys': run(), 'eth_rx': inject()}, clocks=clocks,
        special_overrides={AsyncResetSynchronizer: IdealReset})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix-bytes', type=int, choices=(0, 12, 40, 89), default=12)
    parser.add_argument('--reset-rx', action='store_true')
    parser.add_argument("--queued-frame", action="store_true", help="Commit full frame, reset after prefix reaches sys")
    parser.add_argument("--common-cdc", action="store_true", help="Use upstream common-reset RX FIFO in model only")
    parser.add_argument("--reset-mac", action="store_true", help="Model-only MAC sys + test consumer reset, coherent TX FIFO")
    parser.add_argument("--network-reset", action="store_true", help="Exercise actual project NetworkReset helper")
    args = parser.parse_args()
    if args.network_reset and (not (args.queued_frame and args.reset_rx) or args.reset_mac or args.common_cdc):
        parser.error("Network reset requires queued RX reset without other reset strategies")
    if args.reset_mac and not (args.reset_rx and args.queued_frame and args.common_cdc):
        parser.error("MAC reset model requires queued frame, RX reset and common RX CDC")
    result = trial(args.prefix_bytes, args.reset_rx, args.queued_frame, args.common_cdc, args.reset_mac, args.network_reset)
    print(json.dumps(result, indent=2), flush=True)
    if not args.queued_frame and (args.prefix_bytes == 0 or (args.prefix_bytes == 12 and args.reset_rx)):
        assert [row['rx'] for row in result['frames']] == [1, 2, 3], result
        assert all(row['crc'] == 0 for row in result['frames']), result
    if not args.queued_frame and args.prefix_bytes == 12 and not args.reset_rx:
        assert [row['rx'] for row in result['frames']] == [0, 1, 2], result
        assert [row['crc'] for row in result['frames']] == [1, 1, 1], result
    if args.reset_mac or args.network_reset:
        assert [row['rx'] for row in result['frames']] == [1, 2, 3], result
        assert all(row['crc'] == 0 and row['errors'] == 0 and row['preamble'] == 0 for row in result['frames']), result
    print('PASS: scenario completed; counters above are observations, not a hardware diagnosis')
