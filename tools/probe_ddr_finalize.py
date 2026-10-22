#!/usr/bin/env python3
"""Isolate finalization and normalization from an admitted mapped snapshot."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=ROOT/'build/zc706-integrated-yosys-fixed/gateware/gateware'
yosys=ROOT/'build/tools/oss-cad-suite/bin/yosys'
cells=yosys.parent.parent/'share/yosys/xilinx'
rows=[]
for mode,extra in [('finalized','synth_xilinx -top top -run finalize:check;'),('normalized','synth_xilinx -top top -run finalize:check; bufnorm -conn;'),('normalized_flat','synth_xilinx -top top -run finalize:check; bufnorm -flat -conn;'),('top_only','synth_xilinx -top top -run finalize:check; select top; bufnorm -conn;'),('full','synth_xilinx -flatten -arch xc7 -top top;')]:
 source = f'read_verilog -lib {cells}/cells_sim.v {cells}/cells_xtra.v; read_json {w}/mapped.json;'
 if mode == 'full': source = f'read_rtlil {w}/elaborated.il;'
 with (w/(mode+'.log')).open('w') as log:
  subprocess.run([str(yosys),'-p',f'{source} {extra} select top; write_json -selected {w}/{mode}.json'],stdout=log,stderr=subprocess.STDOUT,check=True)
 x=json.loads((w/(mode+'.json')).read_text())['modules']['top']
 pad=x['ports']['ddram_dq']['bits'];io=[b for c in x['cells'].values() if c['type']=='IOBUF' for b in c['connections']['IO']]
 rows.append(dict(mode=mode,matched=len(set(pad)&set(io)),expected=len(pad),buffers=sum(c['type'] in ('$buf','$_BUF_') for c in x['cells'].values())))
 print(rows[-1],flush=True)
(w/'finalization-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
