#!/usr/bin/env python3
"""Fail closed if the ARP self-test no longer contains the intended storage."""
import json
from pathlib import Path


def check(path, no_srl=False):
    module = json.loads(Path(path).read_text())['modules']['top']
    cells = module['cells']
    srls = {n:c for n,c in cells.items() if c['type'].startswith('SRL')}
    if no_srl:
        if srls:
            raise RuntimeError('No-SRL control still contains SRLs')
    else:
        if len(srls) != 8 or any(c['type'] != 'SRL16E' for c in srls.values()):
            raise RuntimeError('ARP test requires exactly eight SRL16E')
        for cell in srls.values():
            tap = sum(int(cell['connections']['A'+str(i)][0]) << i for i in range(4))
            if tap != 6 or cell['connections']['CE'] != ['1']:
                raise RuntimeError('ARP SRL depth/CE differs from the Ethernet header')
    if not any('depacketizer' in n and 'header' in n for n in module['netnames']):
        raise RuntimeError('ARP header logic absent')
    return {'result':'PASS', 'srl_count':len(srls), 'no_srl_control':no_srl}
