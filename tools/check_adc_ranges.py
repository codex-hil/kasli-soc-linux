#!/usr/bin/env python3
"""On-board range/termination register audit and external CH1 signal captures.

Requires a 1 MHz, 50 mVpp High-Z source on CH1 of each card. External
termination is physically tested on CH1 only; other channels get CSR audits.
"""
import argparse
import json
from pathlib import Path
import time
from fmc_adc import ADC, Registers


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csr-json', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    result = dict(result='FAIL', external_channels=[1], cards={})
    opened = []
    try:
        for card in (1, 2):
            r = Registers(a.csr_json, '/dev/uio0', card)
            opened.append(r)
            if r.read('adc_control') != 1 or r.read('adc_ssr') != 0:
                raise RuntimeError('Requires stopped/disconnected card')
            adc = ADC(r)
            adc.initialize()
            record = dict(training=adc.calibrate(), settings=[], captures=[])
            result['cards'][str(card)] = record
            adc.pattern()
            # Every range, normal/calibration mode and termination on all channels.
            for channel in range(4):
                for fs in (5, .5, .05):
                    for cal in (False, True):
                        for term in (False, True):
                            ssr = adc.set_input(channel, fs, term, cal)
                            record['settings'].append(dict(channel=channel+1, full_scale_v=fs,
                                calibration=cal, termination=term, ssr=ssr))
                r.write('adc_ssr', 0)
            for fs in (5, .5, .05):
                for label, term, cal in [('open',False,False), ('50ohm',True,False),
                                         ('open_repeat',False,False), ('calibration',False,True)]:
                    ssr = adc.set_input(0, fs, term, cal)
                    time.sleep(.1)
                    for repeat in range(4):
                        words = adc.capture()
                        signed = [[(v if v < 32768 else v-65536)//4 for v in row] for row in words]
                        name = f'card{card}-{fs:g}V-{label}-{repeat}.json'
                        (a.output/name).write_text(json.dumps(signed)+'\n')
                        record['captures'].append(dict(file=name, full_scale_v=fs, mode=label,
                            ssr=ssr, frame_errors=r.read('adc_errors')))
            record['adc_a2'] = adc.reg(2)
        result['result'] = 'CAPTURED'
    finally:
        for r in opened:
            r.write('adc_ssr', 0)
            r.write('adc_control', 1)
            r.mem.close()
        (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result['result'])


if __name__ == '__main__':
    main()
