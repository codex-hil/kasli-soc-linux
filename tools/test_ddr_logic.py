#!/usr/bin/env python3
"""Run DDR logic simulations and retain their evidence for packaging."""
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
log = ROOT/'build/zc706-ddr/tests/logic.log'
log.parent.mkdir(parents=True, exist_ok=True)
with log.open('w') as output:
    for name in ('pl_ddr_bist.py', 'pl_ddr_frontend.py'):
        subprocess.run([sys.executable, ROOT/'tests'/name], stdout=output,
            stderr=subprocess.STDOUT, check=True)
print(log.read_text())
