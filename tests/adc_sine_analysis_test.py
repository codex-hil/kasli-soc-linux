#!/usr/bin/env python3
"""Check sine extraction and rejection of absent, wrong-frequency or clipped signals."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('analysis',Path(__file__).resolve().parents[1]/'tools/analyze_adc_sine.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np=module.np
rng=np.random.default_rng(706)
t=np.arange(1024)/100e6
values=17+780*np.sin(2*np.pi*1.0023e6*t+.63)+rng.normal(0,2,1024)
r,_=module.fit_sine(values,100e6)
assert r['passed'] and abs(r['frequency_hz']-1.0023e6)<100
assert abs(r['vpp_adc_codes']-1560)<2 and abs(r['dc_adc_codes']-17)<1
for bad in [np.zeros(1024), rng.normal(0,3,1024), 780*np.sin(2*np.pi*2e6*t)]:
 assert not module.fit_sine(bad,100e6)[0]['passed']
values[10]=8191
assert not module.fit_sine(values,100e6)[0]['passed']
print('PASS: frequency/amplitude/DC with noise; rejects absent signal, noise, wrong frequency and clipping')
