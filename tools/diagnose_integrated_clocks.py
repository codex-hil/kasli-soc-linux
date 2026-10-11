#!/usr/bin/env python3
"""Read-only bounded connectivity probe; run through tools/environment.py."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from integrated_nextpnr import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--xdc', type=Path, required=True)
    parser.add_argument('--chipdb', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--backend', type=Path, help='Reuse an isolated diagnostic backend')
    parser.add_argument('--topology-only', action='store_true',
                        help='Ignore occupancy and programmability; diagnostic only')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    binary = args.backend.resolve() if args.backend else prepare()
    command = [str(binary), '--device', 'xc7z045ffg900-2',
               '--json', str(args.json.resolve()), '--no-pack', '--no-place',
               '-o', 'xdc='+str(args.xdc.resolve()), '--chipdb', str(args.chipdb.resolve()),
               '--router', 'router2']
    env = dict(os.environ, NEXTPNR_CLOCK_BFS='1', NEXTPNR_CLOCK_ONLY='1',
               NEXTPNR_CLOCK_DIAGNOSTIC_EXIT='1')
    if args.topology_only:
        env['NEXTPNR_CLOCK_TOPOLOGY'] = '1'
    else:
        env.pop('NEXTPNR_CLOCK_TOPOLOGY', None)
    logfile = args.output/'connectivity.log'
    with logfile.open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                env=env, timeout=120)
    text = logfile.read_text()
    if 'Clock diagnostic complete; intentionally skipping router' not in text:
        raise RuntimeError('Diagnostic did not reach its controlled exit; inspect '+str(logfile))
    nets = {}
    pattern = r'Clock-BFS: net=(\S+) found=(\d+) forward=(\d+) backward=(\d+) pending_forward=(\d+) pending_backward=(\d+) reason=(\S+)'
    for match in re.finditer(pattern, text):
        name, found, forward, backward, pending_forward, pending_backward, reason = match.groups()
        nets[name] = dict(found=bool(int(found)), forward=int(forward), backward=int(backward),
                          pending_forward=int(pending_forward), pending_backward=int(pending_backward), reason=reason)
    if len(nets) != 2:
        raise RuntimeError('Expected both clock nets, got '+str(list(nets)))
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(hardware_access=False, input_files_modified=False,
                  diagnostic_search_binds_resources=False, writes_bitstream=False,
                  search_subset='PIP names containing CLK, BUFG or MMCM',
                  topology_only=args.topology_only, nets=nets, diagnostic_exit_code=result.returncode,
                  sha256={str(p): digest(p) for p in [args.json, args.xdc, args.chipdb, binary, logfile]})
    (args.output/'connectivity.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(nets, indent=2))


if __name__ == '__main__':
    main()
