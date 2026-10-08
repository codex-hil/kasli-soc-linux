#!/usr/bin/env python3
"""Verify that the isolated overlay cannot corrupt the installed database."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('overlay', Path(__file__).resolve().parents[1]/'tools/adc_termination_db.py')
overlay = importlib.util.module_from_spec(spec); spec.loader.exec_module(overlay)


class Overlay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.original = self.root/'original'; self.original.mkdir()
        (self.original/'segbits_liob33.db').write_text('LIOB33.IOB_Y0.GENERIC.IN_ONLY !38_100 !39_97 38_118\n')
        (self.original/'routing.db').write_text('untouched\n')
        (self.root/'patches').mkdir()
        self.mapping = dict(repeated_baseline_identical=True, all_on_union_verified=True,
            features={'LIOB33.DIFF.DIFF_TERM':['38_100','39_97']},
            input_only_aliases={'LIOB33.IOB_Y0.LVDS_25.IN_ONLY':dict(
                source_feature='LIOB33.IOB_Y0.GENERIC.IN_ONLY',omit_bits=['!38_100','!39_97'])},
            source_db_sha256={'segbits_liob33.db':hashlib.sha256((self.original/'segbits_liob33.db').read_bytes()).hexdigest()})

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self):
        (self.root/'patches/prjxray-hr-diff-term.json').write_text(json.dumps(self.mapping))
        with patch.object(overlay,'ROOT',self.root):
            return overlay.prepare(self.original)

    def test_overlay_preserves_source_even_when_destination_is_symlink(self):
        target = self.root/'build/zc706-adc/termination-db/zynq7'; target.mkdir(parents=True)
        (target/'segbits_liob33.db').symlink_to(self.original/'segbits_liob33.db')
        before = (self.original/'segbits_liob33.db').read_bytes()
        self.prepare(); self.prepare()
        self.assertEqual((self.original/'segbits_liob33.db').read_bytes(),before)
        self.assertFalse((target/'segbits_liob33.db').is_symlink())
        self.assertTrue((target/'routing.db').is_symlink())
        content = (target/'segbits_liob33.db').read_text()
        self.assertIn('LIOB33.IOB_Y0.LVDS_25.IN_ONLY 38_118\n',content)
        self.assertIn('LIOB33.DIFF.DIFF_TERM 38_100 39_97\n',content)

    def test_unrelated_relaxation_is_rejected(self):
        self.mapping['input_only_aliases']['LIOB33.IOB_Y0.LVDS_25.IN_ONLY']['omit_bits'].append('38_118')
        with self.assertRaisesRegex(RuntimeError,'exactly'):
            self.prepare()

    def test_changed_source_is_rejected(self):
        (self.original/'segbits_liob33.db').write_text('changed\n')
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.prepare()

    def test_unverified_reference_is_rejected(self):
        self.mapping['all_on_union_verified'] = False
        with self.assertRaisesRegex(RuntimeError,'Unverified'):
            self.prepare()


if __name__ == '__main__':
    unittest.main()
