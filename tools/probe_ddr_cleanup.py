#!/usr/bin/env python3
"""Compare alias-removal passes without buffer-normalizing physical inouts."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=ROOT/'build/zc706-integrated-yosys-fixed/gateware/gateware'
yosys=ROOT/'build/tools/oss-cad-suite/bin/yosys'
cells=yosys.parent.parent/'share/yosys/xilinx'
rows=[]
for mode,cmd in [('clean','opt_clean;'),('expr','opt_expr; opt_clean;'),('reset_clean','bufnorm -reset; opt_clean;'),('mapped_alias',f'techmap -map {ROOT}/gateware/yosys/alias_buffers.v; opt_clean;')]:
 with (w/(mode+'.log')).open('w') as log:
  subprocess.run([str(yosys),'-p',f'read_verilog -lib {cells}/cells_sim.v {cells}/cells_xtra.v; read_json {w}/full.json; {cmd} select top; write_json -selected {w}/{mode}.json'],stdout=log,stderr=subprocess.STDOUT,check=True)
 x=json.loads((w/(mode+'.json')).read_text())['modules']['top']
 pad=x['ports']['ddram_dq']['bits'];io=[b for c in x['cells'].values() if c['type']=='IOBUF' for b in c['connections']['IO']]
 rows.append(dict(mode=mode,matched=len(set(pad)&set(io)),expected=len(pad),buffers=sum(c['type'] in ('$buf','$_BUF_') for c in x['cells'].values())))
 print(rows[-1],flush=True)
(w/'cleanup-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
