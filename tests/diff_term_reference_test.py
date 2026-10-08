#!/usr/bin/env python3
"""Check that the reference extractor rejects ambiguous configuration changes."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('extract', ROOT/'tools/analyze_diff_term_reference.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


class Reference(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'db/xc7z020').mkdir(parents=True)
        self.grid = {}
        pairs = []
        for i, kind in enumerate(('LIOB33', 'RIOB33', 'RIOB33')):
            tile = kind+'_X0Y'+str(i)
            self.grid[tile] = dict(type=kind, bits=dict(CLB_IO_CLK=dict(
                baseaddr=hex(0x100+0x100*i), frames=42, offset=10, words=4)))
            pairs.append(dict(p=dict(tile=tile)))
        (self.root/'db/xc7z020/tilegrid.json').write_text(json.dumps(self.grid))
        (self.root/'pins.json').write_text(json.dumps(dict(part='xc7z020clg400-1', pairs=pairs)))
        self.put('off', [])
        self.put('off-repeat', [(0x100,50,1)])  # ECC is not a configurable feature
        for i in range(3):
            self.put('pair'+str(i), [(0x100+0x100*i+30,10,3)])
        self.put('all', [(0x100+0x100*i+30,10,3) for i in range(3)])

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, bits):
        (self.root/(name+'.bits')).write_text(''.join(f'bit_{f:08x}_{w:03d}_{b:02d}\n' for f,w,b in bits))

    def run_extract(self):
        with patch.object(sys,'argv',['extract',str(self.root),'--db',str(self.root/'db')]), contextlib.redirect_stdout(io.StringIO()):
            extract.main()

    def test_consistent_independent_tiles(self):
        self.run_extract()
        self.assertEqual(json.loads((self.root/'mapping.json').read_text())['features'],
                         {'LIOB33.DIFF.DIFF_TERM':['30_03'], 'RIOB33.DIFF.DIFF_TERM':['30_03']})

    def test_unrelated_bit_rejected(self):
        self.put('pair0', [(0x100+30,10,3),(0x500,3,1)])
        with self.assertRaisesRegex(RuntimeError,'outside'):
            self.run_extract()

    def test_inconsistent_tile_mapping_rejected(self):
        self.put('pair2', [(0x300+30,10,4)])
        with self.assertRaisesRegex(RuntimeError,'inconsistent'):
            self.run_extract()

    def test_changed_baseline_rejected(self):
        self.put('off-repeat', [(0x100,10,1)])
        with self.assertRaisesRegex(RuntimeError,'baseline'):
            self.run_extract()

    def test_combined_nonlocal_effect_rejected(self):
        self.put('all', [(0x100+30,10,3)])
        with self.assertRaisesRegex(RuntimeError,'union'):
            self.run_extract()

    def test_ignored_parameter_rejected(self):
        self.put('pair0', [])
        with self.assertRaisesRegex(RuntimeError,'no bits'):
            self.run_extract()


if __name__ == '__main__':
    unittest.main()
