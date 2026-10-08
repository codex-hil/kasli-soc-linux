#!/usr/bin/env python3
"""Package the built, simulation-tested one/two-card target; no hardware writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dual', action='store_true')
args = parser.parse_args()
BUILD = ROOT/('build/zc706-adc-dual' if args.dual else 'build/zc706-adc')
SUPPORT = ROOT/'build/zc706-adc'
label = 'adc-dual' if args.dual else 'adc-j5'
WORK = BUILD/'gateware/gateware'
manifest = json.loads((WORK/'manifest.json').read_text())
bit_hash = hashlib.sha256((WORK/'top.bit').read_bytes()).hexdigest()
if manifest.get('adc_cards', 1) != (2 if args.dual else 1) or manifest['design'] != 'fmc-adc' or not manifest['timing_passed'] or manifest['bitstream_sha256'] != bit_hash:
    raise RuntimeError('Expected a matching successful ADC build')
for test in ('capture', 'receiver', 'dual_capture', 'axi'):
    if 'PASS:' not in (BUILD/f'tests/{test}.log').read_text():
        raise RuntimeError('Required simulation missing: '+test)
soc_validation = json.loads((BUILD/'tests/soc-validation.json').read_text())
if (soc_validation.get('result') != 'PASS' or
        soc_validation.get('top_json_sha256') != hashlib.sha256((WORK/'top.json').read_bytes()).hexdigest() or
        soc_validation.get('csr_json_sha256') != hashlib.sha256((BUILD/'gateware/csr.json').read_bytes()).hexdigest()):
    raise RuntimeError('Simulation must match the packaged netlist and CSR map')
mkimage = ROOT/'build/zc706/buildroot/host/bin/mkimage'
if not mkimage.exists():
    raise RuntimeError('Run make linux BOARD=zc706 to build the pinned U-Boot mkimage')
subprocess.run([mkimage, '-A', 'arm', '-O', 'linux', '-T', 'script', '-C', 'none',
    '-n', 'ZC706 FMC ADC PoC', '-d', ROOT/('boot/zc706-adc-dual.cmd' if args.dual else 'boot/zc706-adc-j5.cmd'), BUILD/(label+'.scr')], check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '0'})
files = {
    label+'.bit': WORK/'top.bit',
    label+'.scr': BUILD/(label+'.scr'),
    label+'.cmd': ROOT/('boot/zc706-adc-dual.cmd' if args.dual else 'boot/zc706-adc-j5.cmd'),
    'csr.json': BUILD/'gateware/csr.json',
    'fmc_adc.py': ROOT/'tools/fmc_adc.py',
    'README.md': ROOT/'docs/zc706-fmc-adc.md',
    'hr-diff-term.md': ROOT/'docs/hr-diff-term.md',
    'nextpnr-termination-manifest.json': SUPPORT/'nextpnr-term/manifest.json',
    'termination-db-manifest.json': SUPPORT/'termination-db/manifest.json',
    'hr-diff-term-mapping.json': ROOT/'patches/prjxray-hr-diff-term.json',
    'build-manifest.json': WORK/'manifest.json',
    'chipdb-manifest.json': SUPPORT/'chipdb/manifest.json',
    'timing.json': WORK/'timing.json',
}
for test in ('capture', 'receiver', 'dual_capture', 'axi'):
    files[f'evidence/{test}.log'] = BUILD/f'tests/{test}.log'
files['evidence/soc-validation.json'] = BUILD/'tests/soc-validation.json'
for stage in range(4):
    files[f'evidence/stage{stage}.log'] = WORK/f'stage{stage}.log'
if args.dual:
    files['dual-acquisition.md'] = ROOT/'docs/zc706-adc-dual.md'
    files['test_adc_hardware.py'] = ROOT/'tools/test_adc_hardware.py'
    files['test_adc_dual_hardware.py'] = ROOT/'tools/test_adc_dual_hardware.py'
validation = BUILD/'hardware/validation.json'
if validation.exists():
    physical = json.loads(validation.read_text())
    driver_hash = hashlib.sha256((ROOT/'tools/fmc_adc.py').read_bytes()).hexdigest()
    if (physical.get('hardware_validated') is True and
            physical.get('bitstream_sha256') == bit_hash and
            physical.get('diagnostic_sha256') == driver_hash):
        for name in ('validation.json', 'result.json', 'samples.bin', 'samples.csv'):
            files['evidence/hardware/'+name] = BUILD/'hardware'/name
checksums = BUILD/'SHA256SUMS'
checksums.write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}\n'
                           for name, path in sorted(files.items())))
files['SHA256SUMS'] = checksums
archive = BUILD/('zc706-fmc-adc-dual.tar.xz' if args.dual else 'zc706-fmc-adc-j5.tar.xz')
with tarfile.open(archive, 'w:xz') as tf:
    for name, path in sorted(files.items()):
        info = tf.gettarinfo(path, arcname=name)
        info.uid = info.gid = 0
        info.uname = info.gname = ''
        info.mtime = 0
        with path.open('rb') as f:
            tf.addfile(info, f)
print(archive)
