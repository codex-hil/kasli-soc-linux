#!/usr/bin/env python3
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=ROOT/'build/zc706-integrated-yosys-fixed/gateware/gateware'
yosys=ROOT/'build/tools/oss-cad-suite/bin/yosys'
for mode,extra in [('elaborated',''),('flattened','flatten;'),('prepared','synth_xilinx -flatten -arch xc7 -top top -run begin:prepare;'),('memory','synth_xilinx -flatten -arch xc7 -top top -run begin:map_memory;'),('fine','synth_xilinx -flatten -arch xc7 -top top -run begin:fine;'),('mapped','synth_xilinx -flatten -arch xc7 -top top -run begin:map_luts;')]:
 with (w/(mode+'.log')).open('w') as log:subprocess.run([str(yosys),'-p',f'read_rtlil {w}/elaborated.il; {extra} select top; write_json -selected {w}/{mode}.json'],stdout=log,stderr=subprocess.STDOUT,check=True)
 x=json.loads((w/(mode+'.json')).read_text())['modules']['top']
 pad=x['ports']['ddram_dq']['bits'];ios=[b for c in x['cells'].values() if c['type']=='IOBUF' for b in c['connections']['IO']]
 print(mode,'matched',len(set(pad)&set(ios)),'of',len(pad),'buffers',sum(c['type']=='$buf' for c in x['cells'].values()))
