#!/usr/bin/env python3
"""Compare stable ADC test words before and after the snapshot BRAM."""
import argparse
import json
import time
from fmc_adc import Registers, ADC

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--csr-json', default='csr.json')
p.add_argument('--device', default='/dev/uio0')
a = p.parse_args()
r = Registers(a.csr_json, a.device)
adc = ADC(r)
results = []
try:
    adc.initialize()
    adc.set_taps([0]*9)
    adc.wait_aligned()
    for value in [0, 0x3fff, 0x1555, 0x2aaa, 0x1235] + [1 << i for i in range(14)]:
        adc.pattern(value)
        time.sleep(.01)
        live = [[r.read('adc_live_low'), r.read('adc_live_high')] for _ in range(8)]
        words = adc.capture()
        results.append(dict(pattern=value, expected=value << 2,
                            live=live, snapshot_first=words[0],
                            snapshot_unique=[sorted(set(row[c] for row in words)) for c in range(4)]))
finally:
    r.write('adc_control', 1)
    r.mem.close()
print(json.dumps(results, indent=2))
