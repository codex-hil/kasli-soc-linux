#!/usr/bin/env python3
"""Offline checks for overlap admission and PHY release on diagnostic failure."""
import unittest
from unittest.mock import patch
from capture_adc_ddr import reset_network_while_capturing


class Registers:
    def __init__(self, statuses=(1,1), supported=True):
        self.map={'constants':{'sfp_network_reset':int(supported)}}
        self.statuses=iter(statuses)
        self.control=8
        self.writes=[]

    def read(self, name):
        if name=='adc_dma_status':return next(self.statuses)
        if name=='sfp_status_control':return self.control
        raise AssertionError(name)

    def write(self, name, value):
        assert name=='sfp_status_control'
        self.writes.append(value)
        self.control=value


class ResetOverlap(unittest.TestCase):
    def test_proven_overlap_preserves_control(self):
        a,b=Registers(),Registers()
        with patch('capture_adc_ddr.time.sleep') as sleep:
            result=reset_network_while_capturing([(1,a,None),(2,b,None)])
        self.assertEqual(a.writes,[24,8])
        self.assertEqual(result['asserted_dma'],{'1':1,'2':1})
        self.assertEqual(result['released_control'],8)
        sleep.assert_called_once_with(.002)

    def test_finished_before_assertion_does_not_write(self):
        a,b=Registers(),Registers((2,))
        with self.assertRaisesRegex(RuntimeError,'missed active'):
            reset_network_while_capturing([(1,a,None),(2,b,None)])
        self.assertEqual(a.writes,[])

    def test_finished_during_assertion_fails_but_releases(self):
        a,b=Registers(),Registers((1,2))
        with self.assertRaisesRegex(RuntimeError,'Could not prove'):
            reset_network_while_capturing([(1,a,None),(2,b,None)])
        self.assertEqual(a.writes,[24,8])

    def test_unsupported_gateware_does_not_write(self):
        a=Registers(supported=False)
        with self.assertRaisesRegex(RuntimeError,'coherent'):
            reset_network_while_capturing([(1,a,None),(2,Registers(),None)])
        self.assertEqual(a.writes,[])

    def test_preexisting_reset_does_not_release_other_state(self):
        a=Registers();a.control=24
        with self.assertRaisesRegex(RuntimeError,'already asserted'):
            reset_network_while_capturing([(1,a,None),(2,Registers(),None)])
        self.assertEqual(a.writes,[])


if __name__=='__main__':unittest.main()
