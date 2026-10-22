#!/usr/bin/env python3
"""Offline simulation of the hardware injector and actual upstream ARP RX."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'gateware'))
from migen.sim import run_simulation
from zc706_arp import ARPSelfTest, HOST_IP, HOST_MAC

for gap in (0, 1, 3):
    dut = ARPSelfTest()
    def control():
        yield dut.gap.storage.eq(gap)
        yield dut.run.storage.eq(1)
        for _ in range(6000):
            yield
        yield dut.run.storage.eq(0)
        for _ in range(300):
            yield
        sent = yield dut.sent.status
        received = yield dut.received.status
        assert sent >= 20 and received == sent, (gap, sent, received)
        assert (yield dut.errors.status) == 0
        assert (yield dut.last_ip.status) == HOST_IP
        mac = (yield dut.last_mac_lo.status) | ((yield dut.last_mac_hi.status) << 32)
        assert mac == HOST_MAC
        assert (yield dut.busy.status) == 0
    run_simulation(dut, control())
print('PASS: actual ARP RX/injector, padded replies, gaps0/1/3, count conservation')
