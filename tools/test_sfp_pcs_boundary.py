#!/usr/bin/env python3
"""Observe real PCS packet boundaries across a simulated decoded-symbol CE gap.

No transceiver model: tests digital PCSTX -> PCSRX only, always-ready consumer.
"""
import json
from migen import Module, Signal
from migen.sim import run_simulation, passive
from liteeth.phy.serial.basex.pcs import PCSTX, PCSRX


def trial(gap_cycles):
    top = Module()
    top.submodules.tx = tx = PCSTX(lsb_first=True)
    top.submodules.rx = rx = PCSRX(lsb_first=True)
    enabled = Signal(reset=1)
    top.comb += [rx.decoder.input.eq(tx.encoder.output[0]),
        rx.decoder.ce.eq(enabled), rx.source.ready.eq(1),
        tx.sgmii_speed.eq(2), rx.sgmii_speed.eq(2)]
    events = []
    frames = []
    state = {'cycle': 0, 'accepted': 0, 'triggered': False}
    @passive
    def monitor():
        data = []
        while True:
            if (yield rx.source.valid):
                byte = (yield rx.source.data)
                last = (yield rx.source.last)
                error = (yield rx.source.error)
                state['accepted'] += 1
                data.append(byte)
                events.append({'cycle': state['cycle'], 'data': byte,
                    'last': last, 'error': error, 'ce': (yield enabled)})
                if last:
                    frames.append({'bytes': len(data), 'error': error,
                        'data_hex': bytes(data).hex()})
                    data = []
            state['cycle'] += 1
            yield
    @passive
    def interrupt():
        while state['accepted'] < 12:
            yield
        if gap_cycles:
            state['triggered'] = True
            yield enabled.eq(0)
            for _ in range(gap_cycles):
                yield
            yield enabled.eq(1)
    def send():
        for _ in range(20):
            yield
        for shot in range(3):
            for index in range(90):
                yield tx.sink.valid.eq(1)
                yield tx.sink.data.eq(0x55 if index < 7 else 0xd5 if index == 7 else index)
                yield
                while not (yield tx.sink.ready):
                    yield
            yield tx.sink.valid.eq(0)
            for _ in range(240):
                yield
        for _ in range(20):
            yield
    run_simulation(top, [send(), monitor(), interrupt()])
    return {'gap_cycles': gap_cycles, 'triggered': state['triggered'],
        'frames': frames, 'events': events}


if __name__ == '__main__':
    for gap in (0, 200):
        result = trial(gap)
        print(json.dumps(result), flush=True)
        if gap == 0:
            assert len(result['frames']) == 3, result
            assert all(f['bytes'] == 90 and not f['error'] for f in result['frames']), result
        else:
            assert result['triggered'], result
            assert [(f['bytes'], f['error']) for f in result['frames']] == [(14, 1), (90, 0), (90, 0)], result
    print('PASS: clean PCS control; CE-gap boundaries characterized (no GTX model)')
