#!/usr/bin/env python3
"""Package the combined ADC/DDR bitstream, matched software and CSR map."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
ROOT=Path(__file__).resolve().parents[1]
work=ROOT/'build/zc706-adc-ddr'
out=work/'package/zc706-adc-ddr'
bit=work/'gateware/gateware/top.bit'
manifest=json.loads((bit.parent/'manifest.json').read_text())
digest=hashlib.sha256(bit.read_bytes()).hexdigest()
if manifest.get('design')!='adc-ddr' or not manifest.get('timing_passed') or manifest.get('bitstream_sha256')!=digest:
    raise RuntimeError('Requires a successful matching ADC DDR build manifest')
if 'PASS: DDR target GP0' not in (work/'tests/axi.log').read_text():
    raise RuntimeError('Requires synthesized AXI/CSR validation')
# Remove only this generated staging directory, preventing stale hardware
# evidence from accompanying a newly rebuilt, unvalidated bitstream.
if out.exists():shutil.rmtree(out)
out.mkdir(parents=True)
for source,name in [(bit,'top.bit'),(bit.parent/'manifest.json','build-manifest.json'),
    (bit.parent/'timing.json','timing.json'),(work/'gateware/csr.json','csr.json'),
    (work/'pl-ddr-test','pl-ddr-test'),(work/'adc-ddr-read','adc-ddr-read'),
    (ROOT/'tools/fmc_adc.py','fmc_adc.py'),(ROOT/'tools/capture_adc_ddr.py','capture_adc_ddr.py'),
    (ROOT/'docs/zc706-adc-ddr.md','README.md'),(ROOT/'sources.lock.json','sources.lock.json'),
    (ROOT/'toolchains.lock.json','toolchains.lock.json')]:
    shutil.copyfile(source,out/name)
for name in ('pl-ddr-test','adc-ddr-read'): (out/name).chmod(0o755)
evidence=ROOT/'evidence/zc706/adc-ddr-20261009'
record=dict(bitstream_sha256=digest,hardware_evidence_matches=False)
validation=evidence/'hardware-validation.json'
if validation.exists():
    hardware=json.loads(validation.read_text())
    record['hardware_evidence_matches']=(hardware.get('result')=='PASS'
        and hardware.get('bitstream_sha256')==digest
        and all(hardware.get('files',{}).get(name)==hashlib.sha256((out/name).read_bytes()).hexdigest()
                for name in ('pl-ddr-test','adc-ddr-read','fmc_adc.py','capture_adc_ddr.py'))
        and hardware.get('files',{}).get('adc-ddr-csr.json')==hashlib.sha256((out/'csr.json').read_bytes()).hexdigest())
    if record['hardware_evidence_matches']:
        shutil.copytree(evidence,out/'evidence')
(out/'artifact-validation.json').write_text(json.dumps(record,indent=2)+'\n')
(out/'README.md').write_text((out/'README.md').read_text().replace(
    '../evidence/zc706/adc-ddr-20261009/',
    'https://github.com/codex-hil/kasli-soc-linux/blob/main/evidence/zc706/adc-ddr-20261009/'))
(out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(out)}\n'
    for f in sorted(out.rglob('*')) if f.is_file() and f.name!='SHA256SUMS'))
archive=work/'zc706-adc-ddr.tar.xz'
with tarfile.open(archive,'w:xz') as tar:
    for file in sorted(out.rglob('*')):
        if not file.is_file():continue
        info=tar.gettarinfo(file,arcname=str(Path(out.name)/file.relative_to(out)))
        info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
        with file.open('rb') as content:tar.addfile(info,content)
archive.with_suffix(archive.suffix+'.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
print(archive)
