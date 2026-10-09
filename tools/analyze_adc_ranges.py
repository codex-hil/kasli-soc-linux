#!/usr/bin/env python3
"""Compare external gain and 50Ω A/B/A captures; raw voltage scale uncalibrated."""
import argparse
import json
from pathlib import Path
import statistics
from analyze_adc_sine import fit_sine, np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    a=p.parse_args()
    capture=json.loads((a.capture/'result.json').read_text())
    result=dict(result='PASS',external_channels=[1],voltage_calibrated=False,cards={})
    for card, record in capture['cards'].items():
        measurements=[]
        for item in record['captures']:
            data=np.array(json.loads((a.capture/item['file']).read_text()),dtype=float)[:,0]
            fit,_=fit_sine(data,100e6)
            fit.pop('passed')  # Prior sine threshold assumes 1 Vpp, widest range.
            fit['nominal_vpp']=fit['vpp_adc_codes']*2*item['full_scale_v']/16384
            measurements.append(item|fit)
        ranges={}
        for fs in (5,.5,.05):
            groups={mode:[m for m in measurements if m['full_scale_v']==fs and m['mode']==mode]
                    for mode in ('open','50ohm','open_repeat','calibration')}
            amplitude={mode:statistics.mean(m['vpp_adc_codes'] for m in rows) for mode,rows in groups.items()}
            ratio=amplitude['50ohm']/amplitude['open']
            drift=amplitude['open_repeat']/amplitude['open']
            isolation=amplitude['calibration']/amplitude['open']
            valid=all(not m['clipped'] and m['frame_errors']==0 and m['r_squared']>.85
                      and abs(m['frequency_hz']-1e6)<10000
                      for mode in ('open','50ohm','open_repeat') for m in groups[mode])
            valid=valid and .45<ratio<.55 and .95<drift<1.05 and isolation<.1
            ranges[str(fs)]=dict(vpp_adc_codes=amplitude,termination_ratio=ratio,
                                repeat_ratio=drift,calibration_leakage_ratio=isolation,passed=valid)
        gains=[ranges['0.5']['vpp_adc_codes']['open']/ranges['5']['vpp_adc_codes']['open'],
               ranges['0.05']['vpp_adc_codes']['open']/ranges['0.5']['vpp_adc_codes']['open']]
        passed=all(v['passed'] for v in ranges.values()) and all(8<g<12 for g in gains)
        result['cards'][card]=dict(ranges=ranges,gain_steps=gains,measurements=measurements,
                                  setting_readbacks=len(record['settings']),adc_a2=record['adc_a2'],passed=passed)
        if not passed:result['result']='FAIL'
    (a.capture/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({c:{'ranges':r['ranges'],'gain_steps':r['gain_steps'],'passed':r['passed']}
                     for c,r in result['cards'].items()},indent=2))
    if result['result']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
