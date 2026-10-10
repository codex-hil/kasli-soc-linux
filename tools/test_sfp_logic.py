#!/usr/bin/env python3
"""Exercise numbered MAC payload CSR control, stalls and error detection."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"gateware"))
from migen import Module
from migen.sim import run_simulation
from liteeth.mac.common import LiteEthMACUserPort
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


if __name__ == "__main__":
    test()
