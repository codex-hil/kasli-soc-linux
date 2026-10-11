#!/usr/bin/env python3
"""Package the matched, physically qualified WR-style phase PLL prototype."""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--dual',action='store_true')
args=p.parse_args()
kind='zc706-wr-pll-dual' if args.dual else 'zc706-wr-pll'
work = ROOT/'build'/kind
bit = work/'gateware/gateware/top.bit'
manifest = json.loads((bit.parent/'manifest.json').read_text())
evidence = ROOT/'evidence/zc706'/('wr-pll-dual-20261011' if args.dual else 'wr-pll-20261011')
validation = json.loads((evidence/'hardware-validation.json').read_text())
digest = hashlib.sha256(bit.read_bytes()).hexdigest()
if manifest.get('design') != 'frequency' or not manifest.get('timing_passed') or manifest.get('bitstream_sha256') != digest or validation.get('bitstream_sha256') != digest or not validation.get('hardware_validated') or not manifest.get('wr_pll'):
    raise RuntimeError('Requires matched successful build and physical qualification')
if args.dual and (manifest.get('wr_pll_cards')!=2 or validation.get('controlled_cards')!=[1,2]):
    raise RuntimeError('Requires physically qualified simultaneous dual-loop build')
for name, expected in validation['files'].items():
    if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
        raise RuntimeError('Hardware qualification file changed: '+name)
out = work/'package'/kind
if out.exists():
    shutil.rmtree(out)  # Only this tool's generated staging directory.
out.mkdir(parents=True)
for source, name in [(bit, 'top.bit'), (bit.parent/'manifest.json', 'build-manifest.json'),
        (work/'gateware/csr.json', 'csr.json'), (ROOT/'tools/measure_fmc_clocks.py', 'measure_fmc_clocks.py'),
        (ROOT/'tools/run_wr_pll.py', 'run_wr_pll.py'),
        (ROOT/'tools/wr_pll_control.py', 'wr_pll_control.py'),
        (work/'i2c.so', 'i2c.so'),
        (ROOT/'tools/fmc_adc.py', 'fmc_adc.py'), (ROOT/'docs'/(kind+'.md'), 'README.md'),
        (ROOT/'sources.lock.json', 'sources.lock.json'), (ROOT/'toolchains.lock.json', 'toolchains.lock.json')]:
    shutil.copyfile(source, out/name)
if args.dual:
    shutil.copyfile(ROOT/'tools/run_wr_pll_dual.py',out/'run_wr_pll_dual.py')
shutil.copytree(evidence, out/'evidence')
shutil.copytree(ROOT/'software/wr_pll',out/'software')
translation=json.loads((ROOT/'build/wr-ddmtd/manifest.json').read_text())
for name, expected in translation['sources'].items():
    source=ROOT/name
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('WR VHDL source changed: '+name)
    dest=out/'sources'/name; dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,dest)
for name in ('tagger.v','manifest.json'):
    shutil.copyfile(ROOT/'build/wr-ddmtd'/name,out/('ddmtd-'+name))
readme = out/'README.md'
text=readme.read_text().replace('../evidence/zc706/'+evidence.name+'/', 'evidence/')
if args.dual:
    text=text.replace('](zc706-wr-pll.md)', '](https://github.com/codex-hil/kasli-soc-linux/blob/main/docs/zc706-wr-pll.md)')
readme.write_text(text+
    '\nOn matching Linux/PL, run `python3 '+('run_wr_pll_dual.py' if args.dual else 'run_wr_pll.py')+
    ' --csr-json csr.json --output result.json --seconds 60 --loss-test`. This is bounded and restores initial Si570 settings. Do not use this clock-only bitstream for ADC acquisition.\n')
(out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n'
    for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
archive = work/(kind+'.tar.xz')
with tarfile.open(archive, 'w:xz') as tar:
    for p in sorted(out.rglob('*')):
        if not p.is_file():
            continue
        info = tar.gettarinfo(p, arcname=str(Path(out.name)/p.relative_to(out)))
        info.uid = info.gid = 0; info.uname = info.gname = ''; info.mtime = 0
        with p.open('rb') as f:
            tar.addfile(info, f)
archive.with_suffix('.xz.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
print(archive)
