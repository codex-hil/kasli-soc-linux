#!/usr/bin/env python3
"""Cross-card CH1 load matrix at widest range; detect common-source coupling."""
import argparse,json,time
from pathlib import Path
from fmc_adc import ADC,Registers
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--csr-json',required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();opened=[];result={'captures':[]}
try:
 for c in (1,2):
  r=Registers(a.csr_json,'/dev/uio0',c);opened.append((c,r,ADC(r)))
 for c,r,adc in opened:
  if r.read('adc_control')!=1 or r.read('adc_ssr')!=0:raise RuntimeError('Requires stopped card')
  adc.initialize();adc.calibrate();adc.pattern()
 for terms in [(False,False),(True,False),(False,True),(True,True),(False,False)]:
  for (c,r,adc),term in zip(opened,terms):adc.set_input(0,5,term)
  time.sleep(.1)
  for c,r,adc in opened:
   words=adc.capture()
   result['captures'].append(dict(card=c,terms=terms,frame_errors=r.read('adc_errors'),
    values=[(row[0] if row[0]<32768 else row[0]-65536)//4 for row in words]))
finally:
 for c,r,adc in opened:r.write('adc_ssr',0);r.write('adc_control',1);r.mem.close()
 a.output.write_text(json.dumps(result)+'\n')
