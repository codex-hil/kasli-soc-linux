#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Sweep physical FMC offset DACs and measure analog ADC snapshots on Linux.

No EEPROM calibration writes. The source is the on-card offset circuit; this
is not external-input gain/linearity or ENOB qualification. Initial receiver
must be stopped with disconnected inputs and DAC clear asserted, so cleanup
can restore a known hardware zero without claiming write-only DAC readback.
"""
import argparse
import csv
import json
from pathlib import Path
import statistics
import struct
import time
from fmc_adc import ADC, Registers


def summarize(words):
    channels = [[] for _ in range(4)]
    for row in words:
        for ch, raw in enumerate(row):
            if raw & 3:
                raise RuntimeError('ADC sample is not left-aligned 14-bit data')
            channels[ch].append((raw if raw < 32768 else raw-65536)//4)
    return [dict(mean=statistics.mean(values), stddev=statistics.pstdev(values),
                 minimum=min(values), maximum=max(values), median=statistics.median(values))
            for values in channels]


def fit(xs, ys):
    mx, my = statistics.mean(xs), statistics.mean(ys)
    xx = sum((x-mx)**2 for x in xs)
    slope = sum((x-mx)*(y-my) for x,y in zip(xs,ys))/xx
    intercept = my-slope*mx
    residual = sum((y-(intercept+slope*x))**2 for x,y in zip(xs,ys))
    variance = sum((y-my)**2 for y in ys)
    return dict(slope_adc_codes_per_dac_code=slope, intercept=intercept,
                r_squared=1-residual/variance if variance else 0,
                span_adc_codes=max(ys)-min(ys),
                maximum_fit_error_codes=max(abs(y-intercept-slope*x) for x,y in zip(xs,ys)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csr-json', required=True)
    p.add_argument('--device', default='/dev/uio0')
    p.add_argument('--output', type=Path, default=Path('adc-offset'))
    p.add_argument('--range', choices=['5V','0.5V','0.05V'], default='5V')
    p.add_argument('--half-span', type=int, default=4096, help='DAC codes around midscale')
    a = p.parse_args()
    if not 8 <= a.half_span <= 4096:
        p.error('Half-span must be 8..4096 codes')
    a.output.mkdir(parents=True, exist_ok=True)
    r = Registers(a.csr_json,a.device); adc = ADC(r)
    initial = dict(control=r.read('adc_control'),ssr=r.read('adc_ssr'),
                   taps=[r.read(f'adc_tap{i}') for i in range(9)])
    # Avoid silently changing an already running acquisition or unknown DAC state.
    if initial['control'] != 1 or initial['ssr'] != 0:
        r.mem.close()
        raise RuntimeError('Expected stopped golden state: control=1, SSR=0, DAC CLR asserted')
    result = dict(result='FAIL', hardware_validated=False, initial=initial,
                  range=a.range, analog_calibrated=False,
                  offset_dac_readback=False, records=[], input_source='on-card offset DAC',
                  source_termination=False, restored=False)
    try:
        adc.initialize()
        if adc.reg(2) != 0:
            raise RuntimeError('Requires FPGA termination ON, ADC termination OFF')
        result['adc_registers']={str(address):adc.reg(address) for address in (1,2)}
        result['calibration']=adc.calibrate()
        adc.pattern()  # Real analog data, never digital test patterns.
        ssr={'5V':0x45,'0.5V':0x11,'0.05V':0x23}[a.range]
        r.write('adc_ssr',sum(ssr << (7*ch) for ch in range(4)))
        time.sleep(0.1)
        codes=[32768 + round(a.half_span*i/4) for i in range(-4,5)]
        with (a.output/'samples.bin').open('wb') as raw:
            def measure(channel, code, direction):
                adc.set_offset_code(channel,code); time.sleep(0.05)
                words=adc.capture()
                raw.write(b''.join(struct.pack('<4H',*row) for row in words))
                record=dict(channel=channel+1,dac_code=code,direction=direction,
                    sample_offset=(len(result['records'])*1024),samples=1024,
                    statistics=summarize(words))
                result['records'].append(record)
                print(json.dumps(record),flush=True)
            for channel in range(4):
                for direction, sweep in [('up',codes),('down',list(reversed(codes)))]:
                    for code in sweep:
                        measure(channel,code,direction)
                adc.set_offset_code(channel,32768); time.sleep(0.05)
                measure(channel,32768,'restored_zero')
        analyses=[]
        for ch in range(4):
            records=[v for v in result['records'] if v['channel']==ch+1]
            up=[v for v in records if v['direction']=='up']
            down=[v for v in records if v['direction']=='down']
            means=[v['statistics'][ch]['mean'] for v in up]
            analysis=fit(codes,means)
            slope=analysis['slope_adc_codes_per_dac_code']
            analysis['channel']=ch+1
            analysis['monotonic']=all((y-x)*slope>0 for x,y in zip(means,means[1:]))
            analysis['hysteresis_max_codes']=max(abs(x['statistics'][ch]['mean']-y['statistics'][ch]['mean'])
                                               for x,y in zip(up,reversed(down)))
            analysis['other_channel_spans_codes']={str(other+1):
                max(v['statistics'][other]['mean'] for v in up)-min(v['statistics'][other]['mean'] for v in up)
                for other in range(4) if other != ch}
            analysis['clipped_samples_seen']=any(v['statistics'][ch]['minimum']==-8192 or
                v['statistics'][ch]['maximum']==8191 for v in records)
            analysis['passed']=(analysis['monotonic'] and analysis['r_squared']>0.995 and
                analysis['span_adc_codes']>10 and not analysis['clipped_samples_seen'] and
                max(analysis['other_channel_spans_codes'].values())<max(5,0.02*analysis['span_adc_codes']))
            analyses.append(analysis)
        result['channels']=analyses
        result['sample_values_checked']=len(result['records'])*1024*4
        with (a.output/'summary.csv').open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['driven_channel','dac_code','direction','read_channel','mean_code','stddev_code','min_code','max_code'])
            for record in result['records']:
                for ch,values in enumerate(record['statistics']):
                    writer.writerow([record['channel'],record['dac_code'],record['direction'],ch+1,
                        values['mean'],values['stddev'],values['minimum'],values['maximum']])
        if not all(ch['passed'] for ch in analyses):
            raise RuntimeError('Offset response checks failed; inspect per-channel measurements')
        result.update(result='PASS',hardware_validated=True)
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        try:
            for ch in range(4):
                adc.set_offset_code(ch,0x8000)
            adc.pattern()
            r.write('adc_ssr',initial['ssr'])
            r.write('adc_control',initial['control'])
            for lane,tap in enumerate(initial['taps']):
                r.write(f'adc_tap{lane}',tap)
            result['restored']=(r.read('adc_control')==initial['control'] and
                                r.read('adc_ssr')==initial['ssr'])
            result['final']=dict(control=r.read('adc_control'),ssr=r.read('adc_ssr'),
                                dac_codes_commanded=[0x8000]*4)
        finally:
            r.mem.close()
            (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    main()
