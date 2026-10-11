#!/usr/bin/env python3
"""Paired-update isolation and failure joining, with simulated actuators."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import gc
from unittest.mock import patch
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_wr_pll_dual import program_pending, loop

class ParallelUpdateTests(unittest.TestCase):
    def test_buses_overlap_without_crossing_corrections(self):
        barrier=threading.Barrier(2)
        class Oscillator:
            def program(self,value):
                barrier.wait(timeout=1)
                return value
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=program_pending([Oscillator(),Oscillator()],
                {0:dict(correction=-13.5),1:dict(correction=-15.1)},pool)
        self.assertEqual(result,{0:-13.5,1:-15.1})

    def test_other_update_finishes_before_failure_returns(self):
        finished=threading.Event()
        class Failed:
            def program(self,value):raise OSError('simulated I2C NACK')
        class Slow:
            def program(self,value):
                time.sleep(.02);finished.set();return value
        with ThreadPoolExecutor(max_workers=2) as pool:
            with self.assertRaisesRegex(RuntimeError,'FMC1'):
                program_pending([Failed(),Slow()],
                    {0:dict(correction=0),1:dict(correction=0)},pool)
            self.assertTrue(finished.is_set())

    def test_cyclic_gc_is_disabled_only_inside_control(self):
        was_enabled=gc.isenabled()
        gc.enable()
        try:
            def control(*args):
                self.assertFalse(gc.isenabled())
                return 'completed'
            with patch('run_wr_pll_dual._loop',side_effect=control):
                self.assertEqual(loop(None,None,[1],1,'test',{}),'completed')
            self.assertTrue(gc.isenabled())
        finally:
            if not was_enabled:gc.disable()

    def test_gc_policy_is_restored_after_control_failure(self):
        was_enabled=gc.isenabled()
        gc.enable()
        try:
            with patch('run_wr_pll_dual._loop',side_effect=RuntimeError('simulated loss')):
                with self.assertRaisesRegex(RuntimeError,'simulated loss'):
                    loop(None,None,[1],1,'test',{})
            self.assertTrue(gc.isenabled())
        finally:
            if not was_enabled:gc.disable()

    def test_fmc2_only_never_programs_fmc1(self):
        class Untuned:
            def program(self,value):raise AssertionError('FMC1 was touched')
        class Tuned:
            def program(self,value):return value
        self.assertEqual(program_pending([Untuned(),Tuned()],
            {1:dict(correction=-15)},None),{1:-15})

if __name__=='__main__':unittest.main()
