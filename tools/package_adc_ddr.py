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
out.mkdir(parents=True,exist_ok=True)
bit=work/'gateware/gateware/top.bit'
manifest=json.loads((bit.parent/'manifest.json').read_text())
if manifest.get('design')!='adc-ddr' or manifest.get('bitstream_sha256')!=hashlib.sha256(bit.read_bytes()).hexdigest():
    raise RuntimeError('Requires a successful matching ADC DDR build manifest')
for source,name in [(bit,'top.bit'),(bit.parent/'manifest.json','build-manifest.json'),
    (bit.parent/'timing.json','timing.json'),(work/'gateware/csr.json','csr.json'),
    (work/'pl-ddr-test','pl-ddr-test'),(work/'adc-ddr-read','adc-ddr-read'),
    (ROOT/'tools/fmc_adc.py','fmc_adc.py'),(ROOT/'tools/capture_adc_ddr.py','capture_adc_ddr.py'),
    (ROOT/'docs/zc706-adc-ddr.md','README.md'),(ROOT/'sources.lock.json','sources.lock.json'),
    (ROOT/'toolchains.lock.json','toolchains.lock.json')]:
    shutil.copyfile(source,out/name)
for name in ('pl-ddr-test','adc-ddr-read'): (out/name).chmod(0o755)
(out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}\n'
    for f in sorted(out.iterdir()) if f.is_file() and f.name!='SHA256SUMS'))
archive=work/'zc706-adc-ddr.tar.xz'
with tarfile.open(archive,'w:xz') as tar:tar.add(out,arcname=out.name)
archive.with_suffix(archive.suffix+'.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
print(archive)
