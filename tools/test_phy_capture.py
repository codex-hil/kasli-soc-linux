#!/usr/bin/env python3
"""Asynchronous passive raw-frame capture regression, no hardware."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateware'))
from migen import Module, ClockDomain, Memory, Signal
from migen.sim import run_simulation, passive
from litex.soc.interconnect import stream
from phy_frame_capture import PHYFrameCapture


def main():
    top = Module()
    top.clock_domains.cd_sys = ClockDomain('sys')
    top.clock_domains.cd_eth_tx = ClockDomain('eth_tx')
    endpoint = stream.Endpoint([('data', 8), ('error', 1)])
    top.submodules.capture = capture = PHYFrameCapture(endpoint, 'eth_tx')
    request = [-1]
    fragment_ready = [False]

    @passive
    def producer():
        yield endpoint.ready.eq(1)
        for shot, length in enumerate((90, 90, 160)):
            while request[0] != shot:
                yield
            if shot == 0:
                for n in range(10):
                    yield endpoint.valid.eq(1)
                    yield endpoint.data.eq(0xee)
                    yield
                yield endpoint.valid.eq(0)
                fragment_ready[0] = True
            while not (yield capture.armed.status):
                yield
            if shot == 0:
                yield endpoint.valid.eq(1)
                yield endpoint.last.eq(1)
                yield
                yield endpoint.valid.eq(0)
                yield endpoint.last.eq(0)
                yield
            for n in range(length):
                yield endpoint.valid.eq(1)
                yield endpoint.data.eq((n + shot) & 255)
                yield endpoint.error.eq(shot == 1 and n == 17)
                yield endpoint.last.eq(n == length - 1)
                yield
            yield endpoint.valid.eq(0)
            yield endpoint.last.eq(0)
            yield endpoint.error.eq(0)
            yield

    def consumer():
        for shot, length in enumerate((90, 90, 160)):
            request[0] = shot
            if shot == 0:
                while not fragment_ready[0]:
                    yield
            yield capture.arm.storage.eq(1)
            yield capture.arm.re.eq(1)
            yield
            yield capture.arm.re.eq(0)
            yield  # Let the sys-domain arm strobe clear the previous done flag.
            assert (yield capture.done.status) == 0
            for _ in range(600):
                if (yield capture.done.status):
                    break
                yield
            else:
                raise AssertionError('Capture timeout')
            assert (yield capture.length.status) == length
            assert (yield capture.error.status) == int(shot == 1), (shot, (yield capture.error.status))
            assert (yield capture.overflow.status) == 0
            for n in range(min(length, 128)):
                yield capture.address.storage.eq(n)
                yield
                assert (yield capture.data.status) == (n + shot) & 255
            for _ in range(5):
                yield
            assert (yield capture.done.status) == 1
    fragment = top.get_fragment()
    for special in fragment.specials:
        if isinstance(special, Memory):
            for port in special.ports:
                if port.dat_r is None:
                    port.dat_r = Signal(special.width)
    clocks = {'sys': 20, 'eth_tx': 8}
    for domain in fragment.clock_domains:
        if domain.name not in clocks:
            clocks[domain.name] = 8 if domain.name.startswith('from') else 20
    run_simulation(fragment, {'sys': consumer(), 'eth_tx': producer()}, clocks=clocks)
    print('PASS: async 125MHz→50MHz capture, fragment rejection, 90-byte frames, error, rearm, 128-byte truncation')


if __name__ == '__main__':
    main()
