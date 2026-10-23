#!/usr/bin/env python3
"""Queued RX FIFO reset characterization; digital model, no PHY or metastability."""
import json
from migen import Module, Signal, ClockDomain, Memory
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.sim import run_simulation
from litex.soc.interconnect import stream


class IdealReset:
    @staticmethod
    def lower(special):
        # Functional reset assertion/release only; no analog/synchronizer timing proof.
        module = Module()
        module.comb += special.cd.rst.eq(special.async_reset)
        return module


def trial(reset, common):
    top = Module()
    top.clock_domains.cd_sys = ClockDomain('sys')
    top.clock_domains.cd_eth_rx = ClockDomain('eth_rx')
    top.submodules.cdc = cdc = stream.ClockDomainCrossing([('data', 8)],
        cd_from='eth_rx', cd_to='sys', depth=32, buffered=False, with_common_rst=common)
    queued, drained, new_done = Signal(), Signal(), Signal()
    result = {'reset_write_domain': reset, 'common_reset': common, 'before': [], 'after': []}
    def writer():
        for _ in range(10):
            yield
        for n in range(10):
            yield cdc.sink.valid.eq(1)
            yield cdc.sink.data.eq(n)
            yield cdc.sink.last.eq(n == 9)
            yield
            while not (yield cdc.sink.ready):
                yield
        yield cdc.sink.valid.eq(0)
        for _ in range(40):
            yield
        yield queued.eq(1)
        while not (yield drained):
            yield
        if reset:
            yield top.cd_eth_rx.rst.eq(1)
            for _ in range(12):
                yield
            yield top.cd_eth_rx.rst.eq(0)
        for _ in range(12):
            yield
        for n in range(3):
            yield cdc.sink.valid.eq(1)
            yield cdc.sink.data.eq(0xa0 + n)
            yield cdc.sink.last.eq(n == 2)
            yield
            while not (yield cdc.sink.ready):
                yield
        yield cdc.sink.valid.eq(0)
        yield new_done.eq(1)
    def reader():
        while not (yield queued):
            yield
        yield cdc.source.ready.eq(1)
        while len(result['before']) < 4:
            yield
            if (yield cdc.source.valid):
                result['before'].append((yield cdc.source.data))
        yield cdc.source.ready.eq(0)
        yield drained.eq(1)
        while not (yield new_done):
            yield
        yield cdc.source.ready.eq(1)
        for _ in range(90):
            yield
            if (yield cdc.source.valid):
                result['after'].append({'data': (yield cdc.source.data), 'last': (yield cdc.source.last)})
    fragment = top.get_fragment()
    for special in fragment.specials:
        if isinstance(special, Memory):
            for port in special.ports:
                if port.dat_r is None:
                    port.dat_r = Signal(special.width)
    clocks = {'sys': 20, 'eth_rx': 8}
    for domain in fragment.clock_domains:
        if domain.name not in clocks:
            clocks[domain.name] = 8 if domain.name.startswith('from') else 20
    run_simulation(fragment, {'sys': reader(), 'eth_rx': writer()}, clocks=clocks,
        special_overrides={AsyncResetSynchronizer: IdealReset})
    return result


if __name__ == '__main__':
    for reset, common in ((False, False), (True, False), (True, True)):
        result = trial(reset, common)
        print(json.dumps(result), flush=True)
        assert result['before'] == [0, 1, 2, 3], result
        values = [beat['data'] for beat in result['after']]
        if not reset:
            assert values == list(range(4, 10)) + [160, 161, 162], result
        if reset and common:
            assert values == [160, 161, 162], result
    print('PASS: clean control and common-reset flush; independent-reset observations retained')
