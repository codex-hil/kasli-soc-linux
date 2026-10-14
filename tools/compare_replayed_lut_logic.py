#!/usr/bin/env python3
"""Check named LUT INIT and original logical pin nets across routed JSONs."""
import argparse,json,re
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for arg in ('reference','candidate','output'):p.add_argument('--'+arg,type=Path,required=True)
a=p.parse_args()
def load(path):
 m=json.loads(path.read_text())['modules']['top'];nets={}
 for n,v in m['netnames'].items():
  for index,bit in enumerate(v['bits']):nets.setdefault(bit,set()).add((n,index))
 return m['cells'],nets
x,xn=load(a.reference);y,yn=load(a.candidate);counts={};issues=[]
for name,c in x.items():
 if c['type']!='SLICE_LUTX':continue
 if name not in y:issues.append({'cell':name,'issue':'missing cell'});continue
 d=y[name]
 orig=c['attributes'].get('X_ORIG_TYPE','')
 if not re.fullmatch(r'LUT[1-6]',orig):continue
 counts[orig]=counts.get(orig,0)+1
 if c['parameters'].get('INIT')!=d['parameters'].get('INIT'):issues.append({'cell':name,'issue':'INIT changed'})
 def pins(cell):return {v:cell['connections'].get(k.removeprefix('X_ORIG_PORT_'),[]) for k,v in cell['attributes'].items() if k.startswith('X_ORIG_PORT_')}
 cp,dp=pins(c),pins(d)
 if set(cp)!=set(dp):issues.append({'cell':name,'issue':'logical port set changed'});continue
 for pin in cp:
  if len(cp[pin])!=1 or len(dp[pin])!=1 or not (xn.get(cp[pin][0],set()) & yn.get(dp[pin][0],set())):
   issues.append({'cell':name,'pin':pin,'issue':'no shared logical net alias'})
r={'hardware_access':False,'qualification':False,'checked_by_original_type':counts,'issue_count':len(issues),'issues':issues,
   'limitation':'Checks INIT and named logical connectivity only. Does not prove emitted physical LUT truth tables, shared pins, SRL/DRAM, generated route-throughs or routing legality.'}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(counts,'issues',len(issues))
