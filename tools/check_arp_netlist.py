#!/usr/bin/env python3
"""Fail closed if the ARP self-test no longer contains the intended storage."""
import json
from pathlib import Path


def check(path, no_srl=False, require_enable=False):
    module = json.loads(Path(path).read_text())['modules']['top']
    cells = module['cells']
    srls = {n:c for n,c in cells.items() if c['type'].startswith('SRL')}
    enable_mode = 'absent'
    if no_srl:
        if require_enable:
            raise RuntimeError('Enabled SRL check requires an SRL image')
        if srls:
            raise RuntimeError('No-SRL control still contains SRLs')
    else:
        if len(srls) != 8 or any(c['type'] != 'SRL16E' for c in srls.values()):
            raise RuntimeError('ARP test requires exactly eight SRL16E')
        for cell in srls.values():
            tap = sum(int(cell['connections']['A'+str(i)][0]) << i for i in range(4))
            if tap != 6:
                raise RuntimeError('ARP SRL depth differs from the Ethernet header')
        enables = {tuple(c['connections']['CE']) for c in srls.values()}
        if len(enables) != 1:
            raise RuntimeError('ARP SRLs must share a common CE')
        enable = next(iter(enables))
        if len(enable) != 1 or (enable != ('1',) and not isinstance(enable[0], int)):
            raise RuntimeError('Unexpected ARP enable signal')
        enable_mode = 'variable' if isinstance(enable[0], int) else 'tied_high'
        if require_enable and enable_mode != 'variable':
            raise RuntimeError('ARP SRL clock enable was lost')
    if not any('depacketizer' in n and 'header' in n for n in module['netnames']):
        raise RuntimeError('ARP header logic absent')
    return {'result':'PASS', 'srl_count':len(srls), 'no_srl_control':no_srl, 'clock_enable_mode':enable_mode}
