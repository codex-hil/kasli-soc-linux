#!/usr/bin/env python3
"""Package the matched, physically qualified small reciprocal counter target."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
work = ROOT/'build/zc706-frequency-small'
bit = work/'gateware/gateware/top.bit'
manifest = json.loads((bit.parent/'manifest.json').read_text())
evidence = ROOT/'evidence/zc706/frequency-20261010/clock-only'
validation = json.loads((evidence/'hardware-validation.json').read_text())
digest = hashlib.sha256(bit.read_bytes()).hexdigest()
if manifest.get('design') != 'frequency' or not manifest.get('timing_passed') or manifest.get('bitstream_sha256') != digest or validation.get('bitstream_sha256') != digest or validation.get('result') != 'PASS':
    raise RuntimeError('Requires matched successful build and physical qualification')
for name, expected in validation['files'].items():
    if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
        raise RuntimeError('Hardware qualification file changed: '+name)
out = work/'package/zc706-frequency'
if out.exists():
    shutil.rmtree(out)  # Only this tool's generated staging directory.
out.mkdir(parents=True)
for source, name in [(bit, 'top.bit'), (bit.parent/'manifest.json', 'build-manifest.json'),
        (work/'gateware/csr.json', 'csr.json'), (ROOT/'tools/measure_fmc_clocks.py', 'measure_fmc_clocks.py'),
        (ROOT/'tools/fmc_adc.py', 'fmc_adc.py'), (ROOT/'docs/zc706-frequency.md', 'README.md'),
        (ROOT/'sources.lock.json', 'sources.lock.json'), (ROOT/'toolchains.lock.json', 'toolchains.lock.json')]:
    shutil.copyfile(source, out/name)
shutil.copytree(evidence.parent, out/'evidence')
readme = out/'README.md'
readme.write_text(readme.read_text().replace('../evidence/zc706/frequency-20261010/', 'evidence/')+
    '\nFor local Linux measurement from this bundle: `python3 measure_fmc_clocks.py --csr-json csr.json --output capture --samples 120`.\n')
(out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n'
    for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
archive = work/'zc706-frequency.tar.xz'
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
