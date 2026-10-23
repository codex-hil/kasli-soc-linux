#!/usr/bin/env python3
"""Offline MMIO sequence checks; never opens hardware devices."""
import unittest
from unittest.mock import patch
import sfp_probe


class StopBeforePacket(Exception):
    pass


class Registers:
    def __init__(self, missing=None):
        self.writes = []
        self.map = {'csr_registers': {f'mac_status_{d}_raw_arm': {}
            for d in ('tx', 'rx', 'rx_cdc', 'crc_input', 'crc_output') if d != missing}}

    def read(self, name):
        if name == 'sfp_status_signature':
            return 0x53465031
        if name == 'sfp_status_status':
            return 63
        if name.endswith('armed'):
            return 1
        return 0

    def write(self, name, value):
        self.writes.append((name, value))
        if name == 'packet_test_start':
            raise StopBeforePacket


class StartupSequence(unittest.TestCase):
    def exercise(self, startup):
        r, observation = Registers(), {}
        with patch.object(sfp_probe, 'status', return_value={}), patch.object(sfp_probe.time, 'sleep'):
            with self.assertRaises(StopBeforePacket):
                sfp_probe.loopback_test(r, 1, observation=observation, capture_startup=startup)
        return r.writes, observation

    def test_probes_survive_mode_sequence_without_rearming(self):
        writes, observation = self.exercise(True)
        reset = writes.index(('sfp_status_control', 26))
        release = writes.index(('sfp_status_control', 10))
        for direction in ('rx_cdc', 'crc_input', 'crc_output'):
            arm = (f'mac_status_{direction}_raw_arm', 1)
            self.assertEqual(writes.count(arm), 1)
            self.assertLess(writes.index(arm), reset)
        for direction in ('tx', 'rx'):
            self.assertGreater(writes.index((f'mac_status_{direction}_raw_arm', 1)), release)
        self.assertIn('after_lock', observation['startup'])

    def test_default_still_arms_after_reset(self):
        writes, observation = self.exercise(False)
        release = writes.index(('sfp_status_control', 10))
        for name, value in writes:
            if name.endswith('_raw_arm'):
                self.assertGreater(writes.index((name, value)), release)
        self.assertNotIn('startup', observation)

    def test_invalid_scope_never_changes_control(self):
        for missing, warmup, error in ((None, 1, ValueError), ('crc_input', 0, RuntimeError)):
            r = Registers(missing)
            with self.assertRaises(error):
                sfp_probe.loopback_test(r, 1, capture_startup=True, warmup=warmup)
            self.assertEqual(r.writes, [])


if __name__ == '__main__':
    unittest.main()
