#!/usr/bin/env python3
"""Check emitted combinational LUT INIT against packed logical pin metadata."""
import argparse,json,re
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for n in ('json','fasm','tilegrid','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();m=json.loads(a.json.read_text())['modules']['top'];g=json.loads(a.tilegrid.read_text());sites={s:(n,t['sites'][s]) for n,t in g.items() for s in t['sites']};features={}
for line in a.fasm.read_text().splitlines():
 r=re.fullmatch(r"(\S+\.INIT)\[63:0\] = 64'b([01]{64})",line)
 if r:features[r[1]]=features.get(r[1],0)|int(r[2],2)
constants={}
for n,v in m['netnames'].items():
 if n in ('$PACKER_GND_NET','$PACKER_VCC_NET'):
  for bit in v['bits']:constants[bit]=int(n=='$PACKER_VCC_NET')
checked=0;cases=0;issues=[];skipped=0
for name,c in m['cells'].items():
 if c['type']!='SLICE_LUTX':continue
 kind=c['attributes'].get('X_ORIG_TYPE','')
 if not re.fullmatch('LUT[1-6]',kind):skipped+=1;continue
 outputs=[o for o in ('O5','O6') if c['connections'].get(o)]
 if len(outputs)!=1:skipped+=1;continue
 site,bel=c['attributes']['NEXTPNR_BEL'].split('/');tile,stype=sites[site]
 # FASM slice X index is the site-local left/right index.
 peers=[s for s in g[tile]['sites'] if s.startswith('SLICE_')];x=int(site.split('_X')[1].split('Y')[0]);base=min(int(s.split('_X')[1].split('Y')[0]) for s in peers)
 key=f'{tile}.{stype}_X{x-base}.{bel[0]}LUT.INIT'
 if key not in features:issues.append({'cell':name,'issue':'missing INIT feature'});continue
 mapping={int(v[1:]):int(k.rsplit('_',1)[1][1:])-1 for k,v in c['attributes'].items() if re.fullmatch('X_ORIG_PORT_A[1-6]',k) and re.fullmatch('I[0-5]',v)}
 logical=int(c['parameters']['INIT'],2);bad=0;valid=0
 for physical in range(64 if outputs[0]=='O6' else 32):
  if any(c['connections'].get(f'A{i+1}') and c['connections'][f'A{i+1}'][0] in constants and ((physical>>i)&1)!=constants[c['connections'][f'A{i+1}'][0]] for i in range(6 if outputs[0]=='O6' else 5)):continue
  index=sum(((physical>>pin)&1)<<i for i,pin in mapping.items());valid+=1
  bad+=((features[key]>>physical)&1)!=((logical>>index)&1)
 checked+=1;cases+=valid
 if bad:issues.append({'cell':name,'issue':'truth table mismatch','cases':valid,'errors':bad})
r={'hardware_access':False,'qualification':False,'checked_luts':checked,'checked_assignments':cases,'skipped_luts':skipped,'issue_count':len(issues),'issues':issues[:100],'issues_truncated':len(issues)>100,'limitation':'Finite combinational LUT INIT/pin audit only; excludes SRL/DRAM, disconnected or multiple outputs and routing legality.'};a.output.write_text(json.dumps(r,indent=2)+'\n');print(checked,cases,'issues',len(issues))
