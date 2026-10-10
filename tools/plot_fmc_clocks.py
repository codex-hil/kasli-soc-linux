#!/usr/bin/env python3
"""Plot physical reciprocal measurements; optional existing ADC plotting dependencies."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build/adc-plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('result', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
d = json.loads(a.result.read_text())
if not d.get('hardware_validated'):
    p.error('Requires a completed hardware-qualified measurement')
rows = d['samples']
t = [r['elapsed_seconds']-rows[0]['elapsed_seconds'] for r in rows]
fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, layout='constrained')
for name, label in [('frequency', 'FMC LPC'), ('frequency2', 'FMC HPC')]:
    axes[0].plot(t, [r[name]['offset_ppm'] for r in rows], label=label)
axes[0].set_ylabel('Offset vs FCLK (ppm)')
axes[0].legend()
axes[1].plot(t, [r['intercard_ppm'] for r in rows], color='#247c54')
axes[1].set_ylabel('LPC / HPC offset (ppm)')
axes[1].set_xlabel('Elapsed measurement time (s)')
for ax in axes:
    ax.grid(alpha=.25)
    ax.ticklabel_format(axis='y', style='plain', useOffset=False)
fig.suptitle('ZC706 / two FMC ADC v6.1 — reciprocal frequency measurement\n'
             'Nominal 100 MHz PS reference; 1-second gates; oscillators free-running')
a.output.parent.mkdir(parents=True, exist_ok=True)
for suffix in ('.png', '.svg'):
    fig.savefig(a.output.with_suffix(suffix), dpi=150)
