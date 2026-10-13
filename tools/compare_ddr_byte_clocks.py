#!/usr/bin/env python3
"""Compare physical byte-four serializer clock endpoints; not qualification."""
import argparse
import hashlib
import json
from pathlib import Path

SITES = ['ILOGIC_X1Y255','ILOGIC_X1Y253','ILOGIC_X1Y251','ILOGIC_X1Y259',
         'ILOGIC_X1Y256','ILOGIC_X1Y254','ILOGIC_X1Y260','ILOGIC_X1Y262']

def inspect(directory):
    path=directory/'top_routed.json'
    module=json.loads(path.read_text())['modules']['top']
    nets={}
    for name,net in module['netnames'].items():
        if len(net['bits'])==1:nets.setdefault(net['bits'][0],[]).append((name,net))
    rows=[]
    for dq,site in enumerate(SITES,32):
        matches=[c for c in module['cells'].values() if c['attributes'].get('NEXTPNR_BEL')==site+'/ISERDESE2']
        if len(matches)!=1:raise ValueError('Expected unique serializer at '+site)
        cell=matches[0];ports={}
        for port in ('CLK','CLKB','CLKDIV'):
            bit,=cell['connections'][port];aliases=nets.get(bit,[])
            records=set()
            for _,net in aliases:
                fields=net['attributes'].get('ROUTING','').split(';')
                records.update((fields[i],fields[i+1]) for i in range(0,len(fields)-2,3))
            local=sorted((wire,pip) for wire,pip in records if wire.startswith('SITEWIRE/'+site+'/'))
            if not local:raise ValueError('Missing routed site clock records '+site+'/'+port)
            ports[port]={'aliases':sorted(n for n,_ in aliases),'site_route':local}
        rows.append({'dq':dq,'site':site,'parameters':cell['parameters'],'clocks':ports})
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':rows}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('golden','candidate','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();g,c=inspect(a.golden),inspect(a.candidate)
    differences=[]
    for x,y in zip(g['rows'],c['rows']):
        for key in ('parameters',):
            if x[key]!=y[key]:differences.append({'dq':x['dq'],'kind':key})
        for port in x['clocks']:
            if x['clocks'][port]['site_route']!=y['clocks'][port]['site_route']:
                differences.append({'dq':x['dq'],'kind':port+' local route'})
    report={'hardware_access':False,'qualification':False,'golden':g,'candidate':c,'differences':differences,
            'limitation':'Endpoint records and parameters only; does not prove clock skew, upstream routing, or bitstream correctness.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print('Differences:',differences)

if __name__=='__main__':main()
