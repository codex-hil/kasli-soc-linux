"""Offline negative controls for stale live-runtime status observations."""
import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_sd_runtime_soak import validate_phase_progress


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.before=dict(state='running',pid=42,elapsed_seconds=10,
            cards={card:dict(last=dict(phase=dict(events=100))) for card in ('1','2')})
        self.after=copy.deepcopy(self.before)
        self.after['elapsed_seconds']=12
        for card in self.after['cards'].values():card['last']['phase']['events']=200

    def test_advancing_both_cards(self):
        validate_phase_progress(self.before,self.after)

    def test_stale_file_cannot_qualify(self):
        with self.assertRaisesRegex(RuntimeError,'status did not advance'):
            validate_phase_progress(self.before,self.before)

    def test_one_stalled_phase_counter_cannot_qualify(self):
        self.after['cards']['2']['last']['phase']['events']=100
        with self.assertRaisesRegex(RuntimeError,'stalled or reset'):
            validate_phase_progress(self.before,self.after)

    def test_counter_reset_cannot_qualify(self):
        self.after['cards']['1']['last']['phase']['events']=0
        with self.assertRaisesRegex(RuntimeError,'stalled or reset'):
            validate_phase_progress(self.before,self.after)

    def test_natural_32bit_wrap_is_valid(self):
        self.before['cards']['1']['last']['phase']['events']=0xfffffff0
        self.after['cards']['1']['last']['phase']['events']=0x20
        validate_phase_progress(self.before,self.after)

    def test_service_replacement_cannot_qualify(self):
        self.after['pid']=43
        with self.assertRaisesRegex(RuntimeError,'restarted'):
            validate_phase_progress(self.before,self.after)


if __name__=='__main__':unittest.main()
