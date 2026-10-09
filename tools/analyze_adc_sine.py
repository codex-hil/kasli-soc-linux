#!/usr/bin/env python3
"""Fit/plot captured CH1; nominal ADC rate and range, without voltage calibration."""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build/adc-plot-deps'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def fit_sine(values, fs):
    time = np.arange(len(values))/fs
    def solve(frequency):
        phase = 2*np.pi*frequency*time
        matrix = np.column_stack((np.ones(len(values)), np.sin(phase), np.cos(phase)))
        coefficients = np.linalg.lstsq(matrix, values, rcond=None)[0]
        residual = values-matrix@coefficients
        return float(residual@residual), coefficients, matrix@coefficients
    grid = np.linspace(.9e6, 1.1e6, 41)
    index = min(range(len(grid)), key=lambda i: solve(grid[i])[0])
    lo, hi = grid[max(0,index-1)], grid[min(len(grid)-1,index+1)]
    ratio = (5**.5-1)/2
    for _ in range(60):
        left, right = hi-ratio*(hi-lo), lo+ratio*(hi-lo)
        if solve(left)[0] < solve(right)[0]: hi=right
        else: lo=left
    frequency = (lo+hi)/2
    residual, coefficients, fitted = solve(frequency)
    variance = float((values-values.mean())@(values-values.mean()))
    amplitude = float(np.hypot(coefficients[1], coefficients[2]))
    r_squared = 1-residual/variance if variance else 0
    clipped = bool(np.any((values <= -8192) | (values >= 8191)))
    return dict(frequency_hz=frequency, vpp_adc_codes=2*amplitude,
                nominal_vpp=2*amplitude*10/16384, dc_adc_codes=float(coefficients[0]),
                residual_rms_adc_codes=float(np.sqrt(residual/len(values))),
                r_squared=r_squared, clipped=clipped,
                passed=bool(abs(frequency-1e6)<10000 and amplitude>100 and r_squared>.98 and not clipped)), fitted


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=dict(result='FAIL',sample_rate_hz=100000000,sample_rate_source='nominal; independent Si570s',
                voltage_calibrated=False,inter_card_synchronization=False,cards={})
    fig,axes=plt.subplots(2,1,figsize=(12,7),layout='constrained')
    for card in (1,2):
        results=[]
        for snapshot in range(4):
            with (args.capture/f'card{card}-snapshot{snapshot}.csv').open() as file:
                values=np.array([int(row['ch1_code']) for row in csv.DictReader(file)],dtype=float)
            measurement,fitted=fit_sine(values,100e6)
            measurement['snapshot']=snapshot
            results.append(measurement)
            if snapshot==0:
                time=np.arange(len(values))/100
                ax=axes[card-1]
                ax.plot(time,values,'.',markersize=2,label='CH1 ADC samples')
                ax.plot(time,fitted,linewidth=1,label='sine fit')
                ax.set_xlabel('Time from this card’s snapshot start (µs)')
                ax.set_ylabel('Signed 14-bit ADC codes')
                ax.set_title(f"{'LPC' if card==1 else 'HPC'} CH1: {measurement['frequency_hz']/1e6:.6f} MHz, "
                             f"{measurement['vpp_adc_codes']:.1f} codes p-p, R²={measurement['r_squared']:.7f}")
                ax.grid(alpha=.25);ax.legend()
        result['cards'][str(card)]=results
    result['result']='PASS' if all(r['passed'] for rs in result['cards'].values() for r in rs) else 'FAIL'
    fig.suptitle('AFG1062: requested 1 MHz / 1 Vpp, High-Z — independent FMC CH1 snapshots\nNominal 100 MS/s; ADC voltage scale uncalibrated; traces have separate epochs')
    args.output.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.output/'waveforms.png',dpi=160)
    fig.savefig(args.output/'waveforms.svg')
    (args.output/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if result['result']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
