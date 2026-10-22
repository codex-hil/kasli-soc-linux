#!/usr/bin/env python3
"""Minimal clock-enable reproducer and late SRL pass snapshots, no hardware."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
ROOT = Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--skip-trace',action='store_true',help='Skip version-specific late-pass snapshots')
    p.add_argument('--yosys',default='/usr/bin/yosys')
    p.add_argument('--suite',type=Path,default=ROOT/'build/tools/oss-cad-suite',help='Suite providing iverilog and vvp')
    p.add_argument('--cells-sim',default='/usr/share/yosys/xilinx/cells_sim.v')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ('shift.v','tb.v'):shutil.copyfile(ROOT/'diagnostics/yosys-srl-ce'/name,out/name)
    def run(command,log,check=True):
        with (out/log).open('w') as f:
            return subprocess.run(command,cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=60,check=check).returncode
    result={'hardware_access':False,'cases':{},'yosys_version':subprocess.check_output([a.yosys,'-V'],text=True).strip()}
    for mode in (('srl','nosrl') if a.skip_trace else ('srl','nosrl','trace')):
        if mode=='trace':
            script='read_verilog shift.v; synth_xilinx -flatten -abc9 -arch xc7 -top shift -nosrl -run begin:map_luts; write_json before-fixed.json; xilinx_srl -fixed -minlen 3; write_json after-fixed.json; techmap -map +/xilinx/cells_map.v; opt_clean'
        else:script='read_verilog shift.v; synth_xilinx -flatten -abc9 -arch xc7 -top shift '+('-nosrl' if mode=='nosrl' else '')
        script+=f'; write_json {mode}.json; write_verilog -noattr {mode}.v'
        run([a.yosys,'-p',script],mode+'-yosys.log')
        cells=json.loads((out/(mode+'.json')).read_text())['modules']['shift']['cells']
        srls={n:{'type':c['type'],'parameters':c['parameters'],'connections':c['connections']} for n,c in cells.items() if 'SHREG' in c['type'] or c['type'].startswith('SRL')}
        suite=a.suite.resolve()/'bin'
        run([str(suite/'iverilog'),'-g2012','-s','tb','-o',mode+'.vvp','tb.v',mode+'.v',a.cells_sim],mode+'-compile.log')
        code=run([str(suite/'vvp'),mode+'.vvp'],mode+'-simulation.log',check=False)
        transcript=(out/(mode+'-simulation.log')).read_text()
        result['cases'][mode]={'result':'PASS' if code==0 and 'PASS' in transcript else 'FAIL' if code else 'INCONCLUSIVE','returncode':code,'srls':srls,'transcript':transcript}
    for stage in (() if a.skip_trace else ('before-fixed','after-fixed')):
        cells=json.loads((out/(stage+'.json')).read_text())['modules']['shift']['cells']
        result[stage]={n:{'type':c['type'],'parameters':c['parameters'],'connections':c['connections']} for n,c in cells.items() if c['type'] in ('FDRE','FDRE_1') or 'SHREG' in c['type']}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
