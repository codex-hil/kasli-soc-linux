#!/usr/bin/env python3
"""Package the built, simulation-tested one-card target; no hardware writes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'build/zc706-adc'
WORK = BUILD/'gateware/gateware'
manifest = json.loads((WORK/'manifest.json').read_text())
if manifest['design'] != 'fmc-adc' or manifest['hardware_validated']:
    raise RuntimeError('Expected the unvalidated one-card build')
for test in ('capture', 'receiver', 'axi'):
    if 'PASS:' not in (BUILD/f'tests/{test}.log').read_text():
        raise RuntimeError('Required simulation missing: '+test)
mkimage = ROOT/'build/zc706/buildroot/host/bin/mkimage'
if not mkimage.exists():
    raise RuntimeError('Run make linux BOARD=zc706 to build the pinned U-Boot mkimage')
subprocess.run([mkimage, '-A', 'arm', '-O', 'linux', '-T', 'script', '-C', 'none',
    '-n', 'ZC706 J5 ADC PoC', '-d', ROOT/'boot/zc706-adc-j5.cmd', BUILD/'adc-j5.scr'], check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '0'})
files = {
    'adc-j5.bit': WORK/'top.bit',
    'adc-j5.scr': BUILD/'adc-j5.scr',
    'adc-j5.cmd': ROOT/'boot/zc706-adc-j5.cmd',
    'csr.json': BUILD/'gateware/csr.json',
    'fmc_adc.py': ROOT/'tools/fmc_adc.py',
    'README.md': ROOT/'docs/zc706-fmc-adc.md',
    'build-manifest.json': WORK/'manifest.json',
    'chipdb-manifest.json': BUILD/'chipdb/manifest.json',
    'timing.json': WORK/'timing.json',
}
for test in ('capture', 'receiver', 'axi'):
    files[f'evidence/{test}.log'] = BUILD/f'tests/{test}.log'
for stage in range(4):
    files[f'evidence/stage{stage}.log'] = WORK/f'stage{stage}.log'
checksums = BUILD/'SHA256SUMS'
checksums.write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}\n'
                           for name, path in sorted(files.items())))
files['SHA256SUMS'] = checksums
archive = BUILD/'zc706-fmc-adc-j5.tar.xz'
with tarfile.open(archive, 'w:xz') as tf:
    for name, path in sorted(files.items()):
        info = tf.gettarinfo(path, arcname=name)
        info.uid = info.gid = 0
        info.uname = info.gname = ''
        info.mtime = 0
        with path.open('rb') as f:
            tf.addfile(info, f)
print(archive)
