#!/usr/bin/env python3
"""Offline regression for native clock constraints in placed JSON replay."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from integrated_nextpnr import prepare

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'build/zc706-integrated/snapshot-regression')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    backend = args.backend.resolve() if args.backend else prepare()
    evidence = ROOT/'evidence/zc706/integrated-20261011'
    chipdb = ROOT/'build/zc706-integrated/chipdb-cascade-hr/chipdb-xc7z045.bin'
    design = json.loads((evidence/'clock-cascade-reproducer.json').read_text())
    # A real snapshot retains pack=1 even when replay uses --no-pack.
    design['modules']['top']['settings']['pack'] = 1
    missing = args.output/'missing.json'
    missing.write_text(json.dumps(design)+'\n')
    env = dict(os.environ)
    env.pop('NEXTPNR_CLOCK_DIAGNOSTIC_EXIT', None)
    command = [str(backend), '--device', 'xc7z045ffg900-2', '--json', str(missing.resolve()),
               '--no-pack', '--no-place', '--chipdb', str(chipdb)]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=10, env=env)
    (args.output/'missing.log').write_text(result.stdout)
    if result.returncode == 0 or 'Preplaced snapshot lacks clock constraints' not in result.stdout:
        raise RuntimeError('Unconstrained snapshot was not rejected before routing')
    for name, period in [('integratedsoc_ddrclock_clkout0', 12000),
                         ('pma_k7_gtx_basex_s7mmcm1_clkout0', 8000)]:
        attrs = design['modules']['top']['netnames'][name]['attributes']
        for field, value in [('PERIOD', period), ('HIGH', period//2), ('LOW', period//2)]:
            for bound in ('MIN', 'MAX'):
                attrs['NEXTPNR_CLK_'+field+'_'+bound] = value
    restored = args.output/'restored.json'
    restored.write_text(json.dumps(design)+'\n')
    subprocess.run([sys.executable, str(ROOT/'tools/diagnose_integrated_clocks.py'),
                    '--json', str(restored.resolve()), '--xdc', str(evidence/'clock-cascade-reproducer.xdc'),
                    '--chipdb', str(chipdb), '--backend', str(backend),
                    '--output', str(args.output/'restored')], check=True, timeout=130)
    if 'Restored 2 snapshot clock constraints' not in (args.output/'restored/connectivity.log').read_text():
        raise RuntimeError('Clock metadata was not restored')
    result = dict(result='PASS', hardware_access=False, missing_constraints_rejected=True,
                  native_constraints_restored=2, fields_per_clock=6,
                  limitation='Tests replay restoration; full-build snapshot emission and timing remain separate checks.')
    (args.output/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
