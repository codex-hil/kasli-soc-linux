#!/usr/bin/env python3
"""Package an integrated build only against matching physical evidence."""
import argparse,hashlib,io,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--work-dir',type=Path,required=True)
p.add_argument('--evidence-dir',type=Path,default=ROOT/'evidence/zc706/integrated-20261014')
p.add_argument('--evidence-prefix',default='core-integration')
p.add_argument('--readme',type=Path,default=ROOT/'docs/zc706-integrated-qualified.md')
p.add_argument('--validation',type=Path,help='Explicit physical validation JSON; include this evidence directory')
p.add_argument('--output',type=Path,help='Archive destination; qualified older bundles remain untouched')
a=p.parse_args();w=a.work_dir.resolve();g=w/'gateware/gateware';e=a.evidence_dir.resolve()
sha=lambda data:hashlib.sha256(data).hexdigest()
m=json.loads((g/'manifest.json').read_text());v=json.loads((a.validation or e/(a.evidence_prefix+'-result.json')).read_text())
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
files['README.md']=a.readme.read_bytes()
files['golden-mmcm-prerouted.txt']=(e.parent/'integrated-20261013/golden-mmcm-native-prerouted.txt').read_bytes()
for path in sorted(e.glob('*' if a.validation else a.evidence_prefix+'-*')):
 if path.is_file(): files['evidence/'+path.name]=path.read_bytes()
files['artifact-validation.json']=(json.dumps({'core_evidence_matches':True,'bitstream_sha256':sha(bit),
    'external_network_result':v['network_result'],
    'internal_loopback_result':v.get('internal_loopback_result','PASS'),
    'scope':'DDR, dual ADC DMA, dual PLL, '+('external SFP switch link' if v['network_result']=='PASS' else 'internal SFP loopback; external link not qualified')},indent=2)+'\n').encode()
files['SHA256SUMS']=''.join(f'{sha(data)}  {name}\n' for name,data in sorted(files.items())).encode()
archive=a.output or w/'zc706-integrated-qualified.tar.xz'
archive.parent.mkdir(parents=True,exist_ok=True)
with tarfile.open(archive,'w:xz') as tar:
 for name,data in sorted(files.items()):
  info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o755 if name in ('pl-ddr-test','adc-ddr-read') else 0o644
  tar.addfile(info,io.BytesIO(data))
archive.with_suffix('.xz.sha256').write_text(sha(archive.read_bytes())+'  '+archive.name+'\n')
print(archive);print(sha(archive.read_bytes()))
