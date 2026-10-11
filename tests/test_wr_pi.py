#!/usr/bin/env python3
"""Physical closed-loop model: capture, RFREQ bounds and quantized phase."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from wr_pll_control import WRPI

class WRLoopTests(unittest.TestCase):
    def test_capture_and_disturbance(self):
        pi=WRPI(-13000000,-50000000,50000000)
        phase=10.;actual=-13.;dt=.005
        for index in range(30000):
            free=13.5 if index<10000 else 14.25
            phase-=1000*(free+actual)*dt
            actual=pi.update(round(phase*63/10),
                round(.1*(10/63)*1e6*(1<<19)),
                round(.3*dt*(10/63)*1e6*(1<<19)))/1e6
            self.assertLessEqual(abs(actual),50)
        self.assertLess(abs(phase),.3)
        self.assertLess(abs(actual+14.25),.001)

    def test_two_independent_clocks_at_dual_update_interval(self):
        pis=[WRPI(-13000000,-50000000,50000000),WRPI(-15000000,-50000000,50000000)]
        phase=[8.,-7.];actual=[-13.,-15.];dt=.009
        for index in range(30000):
            free=[13.5 if index<10000 else 14.25,15.1]
            for card in range(2):
                phase[card]-=1000*(free[card]+actual[card])*dt
                actual[card]=pis[card].update(round(phase[card]*63/10),
                    round(.15*(10/63)*1e6*(1<<19)),
                    round(.3*dt*(10/63)*1e6*(1<<19)))/1e6
        for card,free in enumerate((14.25,15.1)):
            self.assertLess(abs(phase[card]),.3)
            self.assertLess(abs(actual[card]+free),.001)

    def test_antiwindup_recovery(self):
        pi=WRPI(0,-100,100,shift=4)
        for _ in range(10000):self.assertEqual(pi.update(100,32,4),100)
        self.assertEqual(pi.integrator,0)
        self.assertLess(pi.update(-1,32,4),0)

if __name__=='__main__':unittest.main()
