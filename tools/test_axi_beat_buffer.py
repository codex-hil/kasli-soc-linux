#!/usr/bin/env python3
"""Test an optional upstream-style beat pipeline without changing LiteX checkout."""
import difflib,importlib.util,json,sys,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'gateware'))
from axi_beat_pipeline import buffered_axi_beats
out=ROOT/'build/axi-beat-buffer';out.mkdir(parents=True,exist_ok=True)
context=buffered_axi_beats()
buffered=context.__enter__()
spec=importlib.util.spec_from_file_location('test_axi',ROOT/'upstream/litex/test/interconnect/test_axi.py')
tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
tests.AXI2AXILite=buffered
suite=unittest.TestSuite()
for value in vars(tests).values():
 if isinstance(value,type) and issubclass(value,unittest.TestCase):
  for name in unittest.defaultTestLoader.getTestCaseNames(value):
   if name.startswith(('test_axi2axi','test_axi2wishbone')):suite.addTest(value(name))
assert suite.countTestCases()>0
with (out/'tests.log').open('w') as log:result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
context.__exit__(None,None,None)
record=dict(result='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),hardware_access=False)
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record)
sys.exit(0 if result.wasSuccessful() else 1)
