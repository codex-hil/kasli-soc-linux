#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read actual schema6 chipdb sequential timing coverage without hardware."""
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def audit(path):
    with path.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        def u32(pos):
            return struct.unpack_from('<I', data, pos)[0]
        def rel(pos):
            return pos + struct.unpack_from('<i', data, pos)[0]
        def string(pos):
            ptr = rel(pos)
            return data[ptr:data.find(b'\0', ptr)].decode()
        def items(pos, size):
            return [rel(pos)+size*i for i in range(u32(pos+4))]
        root = rel(0)
        if (u32(root), u32(root+4)) != (0x00ca7ca7, 6):
            raise ValueError('Expected chipdb schema6')
        const = rel(root+76)
        known = [''] + [line.strip()[2:-1].strip() for line in
            (ROOT/'upstream/nextpnr/himbaechel/uarch/xilinx/constids.inc').read_text().splitlines()
            if line.strip().startswith('X(')]
        if len(known) != u32(const):
            raise ValueError('ConstID schema differs')
        names = known + [string(pos) for pos in items(const+4, 4)]
        grades = {}
        for grade in items(root+68, 32):
            cells = {}
            for cell in items(grade+20, 12):
                name = names[u32(cell)]
                if name != 'SLICE_LUTX':
                    continue
                pins = {}
                for pin in items(cell+4, 24):
                    arcs = []
                    for arc in items(pin+16, 56):
                        arcs.append({'clock': names[u32(arc)], 'edge': u32(arc+4),
                            'setup_ps': list(struct.unpack_from('<4i', data, arc+8)),
                            'hold_ps': list(struct.unpack_from('<4i', data, arc+24)),
                            'clock_to_q_ps': list(struct.unpack_from('<4i', data, arc+40))})
                    pins[names[u32(pin)]] = {'flags': u32(pin+4),
                        'comb_arcs': u32(pin+12), 'register_arcs': arcs}
                cells[name] = pins
            if 'SLICE_LUTX' not in cells:
                raise ValueError('No SLICE_LUTX timing variant')
            pins = cells['SLICE_LUTX']
            grades[names[u32(grade)]] = {'pins': pins,
                'srl16e_DI2_register_input': bool(pins.get('DI2', {}).get('register_arcs')),
                'srl16e_O6_register_output': bool(pins.get('O6', {}).get('register_arcs'))}
        return {'chipdb': str(path), 'chipdb_sha256': hashlib.sha256(data).hexdigest(),
                'speed_grades': grades, 'hardware_access': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('chipdb', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--routed', type=Path)
    args = parser.parse_args()
    result = audit(args.chipdb)
    if args.routed:
        module = json.loads(args.routed.read_text())['modules']['top']
        srls = {n: c for n, c in module['cells'].items()
                if c.get('attributes', {}).get('X_ORIG_TYPE') == 'SRL16E'}
        result['routed_sha256'] = hashlib.sha256(args.routed.read_bytes()).hexdigest()
        result['srl16e_cells'] = {n: {'bel': c['attributes'].get('NEXTPNR_BEL'),
            'data_port': 'DI2', 'DI2_connected': bool(c['connections'].get('DI2')),
            'O6_connected': bool(c['connections'].get('O6'))} for n, c in srls.items()}
        result['srl16e_count'] = len(srls)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    for name, grade in result['speed_grades'].items():
        print(name, 'DI2 sequential:', grade['srl16e_DI2_register_input'],
              'O6 sequential:', grade['srl16e_O6_register_output'])


if __name__ == '__main__':
    main()
