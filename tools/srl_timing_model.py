#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Conservative SRL16E six-LUT timing envelope from pinned X-Ray SDF."""
import hashlib
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'upstream/nextpnr/himbaechel/uarch/xilinx/gen'))
import parse_sdf


def model(path):
    sdf = parse_sdf.parse_sdf_file(str(path))
    rows = {}
    for letter in 'ABCD':
        cell = sdf.cells[('LUT_OR_MEM6SHFREG', f'SLICEM/{letter}6LUT')]
        di = next(e for e in cell.entries if isinstance(e, parse_sdf.SetupHoldCheck) and e.pin == 'DI2')
        cq = next(e for e in cell.entries if isinstance(e, parse_sdf.IOPath) and e.from_pin == 'CLK' and e.to_pin == 'O6')
        rows[letter] = {'setup': [di.setup.minv, di.setup.maxv],
                        'hold': [di.hold.minv, di.hold.maxv],
                        'cq': [min(cq.rising.minv, cq.falling.minv), max(cq.rising.maxv, cq.falling.maxv)]}
    common = sdf.cells[('LUT_OR_MEM6SHFREG', 'SLICEM')]
    we = next(e for e in common.entries if isinstance(e, parse_sdf.SetupHoldCheck) and e.pin == 'WE')
    ns = {k: [min(r[k][0] for r in rows.values()), max(r[k][1] for r in rows.values())] for k in ('setup','hold','cq')}
    ns.update(we_setup=[we.setup.minv, we.setup.maxv], we_hold=[we.hold.minv, we.hold.maxv])
    ps = {k: [math.floor(v[0]*1000), math.ceil(v[1]*1000)] for k,v in ns.items()}
    return {'sdf_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'source_ns': rows,
            'envelope_ps': ps, 'scope': 'SRL16E static addresses, rising CLK, 6LUT; DEFAULT SDF envelope, no speed scaling'}


def header(result):
    return '\n'.join(f'static constexpr int srl_{key}_{bound} = {value};'
        for key, pair in result['envelope_ps'].items()
        for bound, value in zip(('min','max'),pair))+'\n'
