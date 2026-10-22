#!/usr/bin/env python3
"""Offline comparison of explicit IOBUF connectivity across alias cleanup."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
yosys=ROOT/'build/tools/oss-cad-suite/bin/yosys'
out=ROOT/'build/yosys-inout';out.mkdir(parents=True,exist_ok=True)
rows=[]
for mode,cleanup in [('plain',''),('conn','bufnorm -conn;'),('flat','bufnorm -flat -conn;'),('roundtrip',''),('roundtrip_conn','bufnorm -conn;')]:
    script=f'read_verilog {ROOT}/diagnostics/yosys-inout/top.v; synth_xilinx -top top; {cleanup} write_json {out}/{mode}.json'
    if mode.startswith('roundtrip'):
        cells=yosys.parent.parent/'share/yosys/xilinx'
        script=f'read_verilog -lib {cells}/cells_sim.v {cells}/cells_xtra.v; read_verilog {ROOT}/diagnostics/yosys-inout/top.v; hierarchy -check -top top; proc; write_rtlil {out}/elaborated.il; design -reset; read_rtlil {out}/elaborated.il; synth_xilinx -flatten -arch xc7 -top top; {cleanup} write_json {out}/{mode}.json'
    with (out/(mode+'.log')).open('w') as log:subprocess.run([str(yosys),'-p',script],stdout=log,stderr=subprocess.STDOUT,check=True)
    top=json.loads((out/(mode+'.json')).read_text())['modules']['top']
    cell=next(c for c in top['cells'].values() if c['type']=='IOBUF')
    rows.append(dict(mode=mode,pad=top['ports']['pad']['bits'],io=cell['connections']['IO'],connected=top['ports']['pad']['bits']==cell['connections']['IO']))
(out/'result.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
