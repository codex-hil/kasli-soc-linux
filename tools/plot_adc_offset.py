#!/usr/bin/env python3
"""Plot measured offset responses; optional, outside the FPGA build pipeline."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build/adc-plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('results',nargs='+',type=Path)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
measurements=[json.loads(path.read_text()) for path in a.results]
fig,axes=plt.subplots(len(measurements),4,figsize=(15,3.3*len(measurements)),squeeze=False,layout='constrained')
for row,result in enumerate(measurements):
    for channel,ax in enumerate(axes[row]):
        records=[r for r in result['records'] if r['channel']==channel+1]
        for direction,color,marker in [('up','#1768ac','o'),('down','#d95f02','x')]:
            values=[r for r in records if r['direction']==direction]
            ax.errorbar([r['dac_code']-32768 for r in values],
                [r['statistics'][channel]['mean'] for r in values],
                yerr=[r['statistics'][channel]['stddev'] for r in values],
                color=color,marker=marker,markersize=4,linewidth=1,label=direction+' (mean ± σ)')
        analysis=result['channels'][channel]
        ax.set_title(f"CH{channel+1}, ±{result['range']}\nslope {analysis['slope_adc_codes_per_dac_code']:.4f}, R² {analysis['r_squared']:.7f}",fontsize=10)
        ax.set_xlabel('DAC code − 32768')
        if channel==0:ax.set_ylabel('ADC mean (signed 14-bit codes)')
        ax.grid(alpha=.25)
        if row==0 and channel==0:ax.legend(fontsize=8)
fig.suptitle('ZC706 / CERN FMC ADC v6.1 — internal offset sweep, 1024 samples per point\nReal analog ADC data; source termination OFF, FPGA termination ON; uncalibrated',fontsize=12)
a.output.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(a.output.with_suffix('.svg'))
fig.savefig(a.output.with_suffix('.png'),dpi=150)
