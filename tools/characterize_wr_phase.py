#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import time,json
from pathlib import Path
from fmc_adc import Registers, ADC
from wr_pll_control import Si570,phase_snapshot
from run_wr_pll import acquire,reset_phase
from measure_fmc_clocks import reset_counters
import argparse
p=argparse.ArgumentParser(description='Bounded physical DDMTD phase response to +/-1 ppm Si570 steps')
p.add_argument('--csr-json',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
r=Registers(a.csr_json,'/dev/uio0'); s=Si570(r); rows=[]
try:
 ADC(r).initialize()
 other=Registers(a.csr_json,'/dev/uio0',card=2)
 try: ADC(other).initialize()
 finally: other.mem.close()
 reset_counters(r,['frequency','frequency2','frequency_reference']); acquire(r,s); base=s.ppm
 for delta in [0,1,-1,0]:
  s.program(base+delta); reset_phase(r); start=time.monotonic(); segment=[]
  while time.monotonic()-start<3:
   t=time.monotonic()-start; snap=phase_snapshot(r); segment.append(dict(t=t,**snap));time.sleep(.002)
  rows.append(dict(delta_ppm=delta,tune=s.ppm,rows=segment))
  print(delta,segment[0]['phase_ns'],segment[-1]['phase_ns'],flush=True)
finally:
 s.restore();r.write('wr_phase_reset',1);a.output.write_text(json.dumps(rows,indent=2)+'\n');r.mem.close()
