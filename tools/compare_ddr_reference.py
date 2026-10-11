#!/usr/bin/env python3
"""Compare routed ZC706 DDR I/O against a physically validated reference."""
import argparse
import hashlib
import json
from pathlib import Path


def inspect(directory):
    paths=[directory/'top_routed.json', directory/'top.fasm']
    module=json.loads(paths[0].read_text())['modules']['top']
    cells={cell['attributes']['NEXTPNR_BEL']:
           dict(name=name, type=cell['type'], parameters=cell['parameters'])
           for name,cell in module['cells'].items()
           if any(kind in cell['type'] for kind in ('DELAY','SERDES','IOB18'))
           and not name.startswith(('adc_rx.','adc2_rx.'))}
    static={line for line in paths[1].read_text().splitlines()
            if line.startswith(('RIOI','RIOB')) and any(kind in line for kind in
                ('.ILOGIC_Y','.OLOGIC_Y','.IDELAY_Y','.ODELAY_Y','.IOB_Y'))}
    clocks={}
    for suffix in ('ddrclock_clkout0','ddrclock_clkout1'):
        matches=[net for name,net in module['netnames'].items() if name.endswith(suffix)]
        if len(matches)!=1:
            raise ValueError('Expected unique clock '+suffix)
        serialized=matches[0]['attributes']['ROUTING']
        fields=serialized.split(';')
        pips=[fields[index+1] for index in range(0,len(fields)-2,3) if fields[index+1]]
        clocks[suffix]=dict(pips=pips, cascade=any('CASCIN' in p for p in pips),
            fabric=any('CLBLM_' in p or 'CLBLL_' in p for p in pips))
    return dict(cells=cells, static=static, clocks=clocks,
        sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--golden',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    a,b=inspect(args.golden),inspect(args.candidate)
    common=set(a['cells']) & set(b['cells'])
    differences={bel:dict(golden=a['cells'][bel],candidate=b['cells'][bel])
                 for bel in sorted(common) if
                 (a['cells'][bel]['type'],a['cells'][bel]['parameters']) !=
                 (b['cells'][bel]['type'],b['cells'][bel]['parameters'])}
    if not common or not a['static'] or not b['static']:
        raise ValueError('DDR comparison must contain actual I/O cells and FASM')
    report=dict(hardware_access=False, qualification=False,
        io_bel_counts=dict(golden=len(a['cells']),candidate=len(b['cells']),common=len(common)),
        golden_only_bels=sorted(set(a['cells'])-set(b['cells'])),
        candidate_only_bels=sorted(set(b['cells'])-set(a['cells'])),
        io_parameter_differences=differences,
        io_static_counts=dict(golden=len(a['static']),candidate=len(b['static'])),
        removed_static_features=sorted(a['static']-b['static']),
        added_static_features=sorted(b['static']-a['static']),
        clock_routes=dict(golden=a['clocks'],candidate=b['clocks']),
        input_sha256=dict(golden=a['sha256'],candidate=b['sha256']))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ('io_bel_counts','io_static_counts')}))
    print('Parameter differences:',len(differences),'; static differences:',
          len(report['removed_static_features'])+len(report['added_static_features']))

if __name__=='__main__':main()
