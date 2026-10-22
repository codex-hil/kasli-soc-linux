#!/usr/bin/env python3
"""Test an optional upstream-style beat pipeline without changing LiteX checkout."""
import difflib,importlib.util,json,sys,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'upstream/litex/litex/soc/interconnect/axi/axi_full_to_axi_lite.py'
original=path.read_text()
old='''        ax_burst2beat = AXIBurst2Beat(ax_buffer.source, ax_beat)
        self.submodules += ax_buffer, ax_burst2beat'''
new='''        ax_generated = AXIStreamInterface(layout=ax_description(axi.address_width), id_width=axi.id_width) if buffer_beats else ax_beat
        ax_burst2beat = AXIBurst2Beat(ax_buffer.source, ax_generated)
        self.submodules += ax_buffer, ax_burst2beat
        if buffer_beats:
            self.beat_buffer = stream.Buffer(ax_beat.description)
            self.comb += ax_generated.connect(self.beat_buffer.sink)
            self.comb += self.beat_buffer.source.connect(ax_beat)'''
assert original.count(old)==1
candidate=original.replace('def __init__(self, axi, axi_lite):','def __init__(self, axi, axi_lite, buffer_beats=False):',1).replace(old,new)
out=ROOT/'build/axi-beat-buffer';out.mkdir(parents=True,exist_ok=True)
(out/'litex-axi-beat-buffer.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile='a/litex/soc/interconnect/axi/axi_full_to_axi_lite.py',tofile='b/litex/soc/interconnect/axi/axi_full_to_axi_lite.py')))
module=types.ModuleType('axi_beat_candidate');exec(compile(candidate,str(path),'exec'),module.__dict__)
def buffered(*args,**kwargs):return module.AXI2AXILite(*args,buffer_beats=True,**kwargs)
spec=importlib.util.spec_from_file_location('test_axi',ROOT/'upstream/litex/test/interconnect/test_axi.py')
tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
tests.AXI2AXILite=buffered
import litex.soc.interconnect.axi.axi_full_to_wishbone as wb
wb.AXI2AXILite=buffered
suite=unittest.TestSuite()
for value in vars(tests).values():
 if isinstance(value,type) and issubclass(value,unittest.TestCase):
  for name in unittest.defaultTestLoader.getTestCaseNames(value):
   if name.startswith(('test_axi2axi','test_axi2wishbone')):suite.addTest(value(name))
assert suite.countTestCases()>0
with (out/'tests.log').open('w') as log:result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
record=dict(result='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),hardware_access=False)
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record)
sys.exit(0 if result.wasSuccessful() else 1)
