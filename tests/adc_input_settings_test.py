#!/usr/bin/env python3
"""Check independent packed seven-bit channel controls against CERN codes."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from fmc_adc import ADC

class Registers:
    value=0x0abcdef0
    def read(self,name): return self.value
    def write(self,name,value): self.value=value

r=Registers();adc=ADC(r)
for channel in range(4):
    for fs,normal,cal in [(5,0x45,0x44),(.5,0x11,0x40),(.05,0x23,0x42)]:
        for calibration in (False,True):
            for termination in (False,True):
                before=r.value
                adc.set_input(channel,fs,termination,calibration)
                mask=127<<(7*channel)
                assert r.value & ~mask == before & ~mask
                assert (r.value>>(7*channel))&127 == (cal if calibration else normal)|(8 if termination else 0)
for channel,fs in [(-1,5),(4,5),(0,1)]:
    try:adc.set_input(channel,fs)
    except ValueError:pass
    else:raise AssertionError('Invalid setting accepted')
print('Input settings/channel isolation PASS')
