#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check bounded RFREQ tuning on only FMC1, restoring the original setting."""
import argparse
import json
from pathlib import Path
import time
from fmc_adc import Registers, ADC
from measure_fmc_clocks import measure, reset_counters
from wr_pll_control import Si570

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--csr-json', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a=p.parse_args()
r=Registers(a.csr_json, '/dev/uio0')
s=Si570(r)
a.output.parent.mkdir(parents=True,exist_ok=True)
result=dict(card=1, hardware_validated=False, original=s.original, rows=[])
try:
    ADC(r).initialize()
    other=Registers(a.csr_json,'/dev/uio0',card=2)
    try:
        ADC(other).initialize()
    finally:
        other.mem.close()
    reset_counters(r,['frequency','frequency2','frequency_reference'])
    for ppm in (0,5,-5,0):
        actual=s.program(ppm)
        time.sleep(.1)
        row=measure(r,['frequency','frequency2','frequency_reference'],100000000,100000000)
        result['rows'].append(dict(requested_ppm=ppm, actual_ppm=actual, measurement=row))
        print(ppm, row['frequency']['offset_ppm'], row['frequency2']['offset_ppm'], flush=True)
    positive=result['rows'][1]['measurement']['frequency']['offset_ppm']
    negative=result['rows'][2]['measurement']['frequency']['offset_ppm']
    if not 9.5 < positive-negative < 10.5:
        raise RuntimeError('Si570 tuning polarity/sensitivity test failed')
    result['hardware_validated']=True
except Exception as exc:
    result['error']=str(exc)
    raise
finally:
    try:
        s.restore(); result['restored']=True
    finally:
        a.output.write_text(json.dumps(result,indent=2)+'\n'); r.mem.close()
