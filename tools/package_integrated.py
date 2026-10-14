#!/usr/bin/env python3
"""Package the physically checked integrated core, without claiming external SFP."""
import argparse,hashlib,io,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--work-dir',type=Path,required=True)
a=p.parse_args();w=a.work_dir.resolve();g=w/'gateware/gateware';e=ROOT/'evidence/zc706/integrated-20261014'
sha=lambda data:hashlib.sha256(data).hexdigest()
m=json.loads((g/'manifest.json').read_text());v=json.loads((e/'core-integration-result.json').read_text())
bit=(g/'top.bit').read_bytes()
if not m.get('timing_passed') or sha(bit)!=m['bitstream_sha256']:raise ValueError('Timing/hash validation failed')
if not v.get('core_integration_passed') or not v.get('restoration_passed') or v['bitstream_sha256']!=sha(bit):raise ValueError('Matching physical core evidence required')
files={'integrated.bit':bit,'build-manifest.json':(g/'manifest.json').read_bytes(),
       'timing.json':(g/'timing.json').read_bytes(),'csr.json':(w/'gateware/csr.json').read_bytes()}
for n in ('pl-ddr-test','adc-ddr-read','i2c.so'):files[n]=(w/n).read_bytes()
for n in v['files']:
 if n not in files:files[n]=(ROOT/'tools'/n).read_bytes()
 if sha(files[n])!=v['files'][n]:raise ValueError('Physical-test artifact mismatch: '+n)
for n in ('sources.lock.json','toolchains.lock.json'):files[n]=(ROOT/n).read_bytes()
files['README.md']=(ROOT/'docs/zc706-integrated-qualified.md').read_bytes()
files['golden-mmcm-prerouted.txt']=(e.parent/'integrated-20261013/golden-mmcm-native-prerouted.txt').read_bytes()
for path in sorted(e.glob('core-integration-*')):files['evidence/'+path.name]=path.read_bytes()
files['artifact-validation.json']=(json.dumps({'core_evidence_matches':True,'bitstream_sha256':sha(bit),
    'external_network_result':v['network_result'],'scope':'DDR, dual ADC DMA, dual PLL, internal SFP loopback; external link not qualified'},indent=2)+'\n').encode()
files['SHA256SUMS']=''.join(f'{sha(data)}  {name}\n' for name,data in sorted(files.items())).encode()
archive=w/'zc706-integrated-qualified.tar.xz'
with tarfile.open(archive,'w:xz') as tar:
 for name,data in sorted(files.items()):
  info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o755 if name in ('pl-ddr-test','adc-ddr-read') else 0o644
  tar.addfile(info,io.BytesIO(data))
archive.with_suffix('.xz.sha256').write_text(sha(archive.read_bytes())+'  '+archive.name+'\n')
print(archive);print(sha(archive.read_bytes()))
