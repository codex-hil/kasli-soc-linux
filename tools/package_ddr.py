#!/usr/bin/env python3
"""Package independent PL DDR bring-up artifacts; physical status stays explicit."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'build/zc706-ddr'
WORK = BUILD/'gateware/gateware'
manifest = json.loads((WORK/'manifest.json').read_text())
if manifest.get('design') != 'pl-ddr' or not manifest.get('timing_passed'):
    raise RuntimeError('A successful DDR timing/build manifest is required')
if manifest['bitstream_sha256'] != hashlib.sha256((WORK/'top.bit').read_bytes()).hexdigest():
    raise RuntimeError('Bitstream does not match successful build')
if (BUILD/'tests/logic.log').read_text().count('PASS:') != 3:
    raise RuntimeError('Required BIST/CDC/frontend simulations missing')
if 'PASS: DDR target GP0' not in (BUILD/'tests/axi.log').read_text():
    raise RuntimeError('Required synthesized GP0 simulation missing')
files = {
    'pl-ddr.bit': WORK/'top.bit',
    'pl-ddr-test': BUILD/'pl-ddr-test',
    'csr.json': BUILD/'gateware/csr.json',
    'README.md': ROOT/'docs/zc706-pl-ddr.md',
    'build-manifest.json': WORK/'manifest.json',
    'chipdb-manifest.json': BUILD/'chipdb/manifest.json',
    'timing.json': WORK/'timing.json',
    'sources.lock.json': ROOT/'sources.lock.json',
    'toolchains.lock.json': ROOT/'toolchains.lock.json',
    'evidence/bist-frontend.log': BUILD/'tests/logic.log',
    'evidence/axi.log': BUILD/'tests/axi.log',
}
for stage in range(4):
    files[f'evidence/stage{stage}.log'] = WORK/f'stage{stage}.log'
for name in ('validation.json', 'program.log'):
    path = BUILD/'hardware'/name
    if path.exists():
        files['evidence/hardware/'+name] = path
checksums = BUILD/'SHA256SUMS'
checksums.write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}\n'
                           for name, path in sorted(files.items())))
files['SHA256SUMS'] = checksums
archive = BUILD/'zc706-pl-ddr-bringup.tar.xz'
with tarfile.open(archive, 'w:xz') as tf:
    for name, path in sorted(files.items()):
        info = tf.gettarinfo(path, arcname=name)
        info.uid = info.gid = 0
        info.uname = info.gname = ''
        info.mtime = 0
        with path.open('rb') as f:
            tf.addfile(info, f)
print(archive)
