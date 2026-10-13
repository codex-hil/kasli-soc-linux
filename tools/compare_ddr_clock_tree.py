#!/usr/bin/env python3
"""Compare routed DDR clock tree PIPs/parameters without accessing hardware."""
import argparse
import hashlib
import json
from pathlib import Path

SUFFIXES=('ddrclock_clkout0','ddrclock_clkout1','ddrclock_clkout_buf0','ddrclock_clkout_buf1')
def inspect(directory):
    path=directory/'top_routed.json';m=json.loads(path.read_text())['modules']['top'];clocks={}
    for suffix in SUFFIXES:
        matches=[net for name,net in m['netnames'].items() if name.endswith(suffix)]
        if len(matches)!=1:raise ValueError('Expected one '+suffix)
        fields=matches[0]['attributes']['ROUTING'].split(';')
        pips=sorted(set(fields[i+1] for i in range(0,len(fields)-2,3) if fields[i+1]))
        if not pips:raise ValueError('Unrouted '+suffix)
        clocks[suffix]=pips
    matches=[c for c in m['cells'].values() if c['attributes'].get('NEXTPNR_BEL')=='MMCME2_ADV_X1Y4/MMCME2_ADV']
    if len(matches)!=1:raise ValueError('Expected DDR MMCM at fixed site')
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'clocks':clocks,'mmcm_parameters':matches[0]['parameters']}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('golden','candidate','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();g,c=inspect(a.golden),inspect(a.candidate);d={}
    for suffix in SUFFIXES:
        x,y=set(g['clocks'][suffix]),set(c['clocks'][suffix]);d[suffix]={'golden_count':len(x),'candidate_count':len(y),'removed_count':len(x-y),'added_count':len(y-x),'removed':sorted(x-y)[:256],'added':sorted(y-x)[:256],'details_truncated':max(len(x-y),len(y-x))>256}
    r={'hardware_access':False,'qualification':False,'golden_sha256':g['sha256'],'candidate_sha256':c['sha256'],'mmcm_parameters_equal':g['mmcm_parameters']==c['mmcm_parameters'],'routes':d,'limitation':'Route feature comparison does not measure relative phase/skew or establish causality.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print('MMCM parameters equal:',r['mmcm_parameters_equal'])
    for n,v in d.items():print(n,v['golden_count'],v['candidate_count'],'removed',v['removed_count'],'added',v['added_count'])
if __name__=='__main__':main()
