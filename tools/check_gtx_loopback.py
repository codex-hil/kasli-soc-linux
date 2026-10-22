#!/usr/bin/env python3
"""Strict synthesized GTX PCS admission: exhaustively check CDR hold for all modes."""
import argparse
import hashlib
import json
from pathlib import Path


def check(path, routed=False):
    path = Path(path)
    top = json.loads(path.read_text())['modules']['top']
    channels = [c for c in top['cells'].values() if c['type'] == 'GTXE2_CHANNEL']
    if len(channels) != 1:
        raise RuntimeError('Expected exactly one GTX channel')
    channel = channels[0]
    if routed:
        constants = {}
        for cell in top['cells'].values():
            if cell['type'] in ('PSEUDO_GND', 'PSEUDO_VCC'):
                bits = cell['connections'].get('Y', [])
                if len(bits) != 1 or bits[0] in constants:
                    raise RuntimeError('Ambiguous packed constant driver')
                constants[bits[0]] = '1' if cell['type'] == 'PSEUDO_VCC' else '0'
        channel['connections']['LOOPBACK'] = [channel['connections']['LOOPBACK'+str(i)][0] for i in range(3)]
        channel['connections']['RXOUTCLKSEL'] = [constants.get(channel['connections']['RXOUTCLKSEL'+str(i)][0]) for i in range(3)]
        hold_bit = channel['connections']['RXCDRHOLD'][0]
        for cell in top['cells'].values():
            if cell['type'] != 'SLICE_LUTX' or cell['connections'].get('O6') != [hold_bit]:
                continue
            attrs = cell['attributes']
            if attrs.get('X_ORIG_TYPE') != 'LUT3' or not attrs.get('NEXTPNR_BEL'):
                raise RuntimeError('Unsupported/unplaced packed CDR decoder')
            mapped = {}
            for key, value in attrs.items():
                if key.startswith('X_ORIG_PORT_'):
                    if value in mapped:raise RuntimeError('Duplicate original LUT port')
                    mapped[value] = cell['connections'][key.removeprefix('X_ORIG_PORT_')]
            if set(mapped) != {'I0','I1','I2','O'}:
                raise RuntimeError('Incomplete packed LUT pin map')
            cell['type'] = 'LUT3'
            cell['connections'] = mapped
            cell['port_directions'] = {k: 'output' if k == 'O' else 'input' for k in mapped}
    for name, expected in [('RXBUF_EN', 'TRUE'), ('RX_XCLK_SEL', 'RXREC')]:
        if channel['parameters'].get(name) != expected:
            raise RuntimeError('Unsupported GTX parameter: ' + name)
    if channel['connections'].get('RXOUTCLKSEL') != ['0', '1', '0']:
        raise RuntimeError('Expected PMA RXOUTCLK selection 010')
    loop = channel['connections']['LOOPBACK']
    hold = channel['connections']['RXCDRHOLD']
    if len(loop) != 3 or len(set(loop)) != 3 or not all(isinstance(b, int) for b in loop):
        raise RuntimeError('Expected three distinct dynamic loopback bits')
    if len(hold) != 1:raise RuntimeError('Expected one CDR hold pin')
    drivers = [(name, c) for name, c in top['cells'].items()
               if any(hold[0] in bits for port, bits in c['connections'].items()
                      if c['port_directions'].get(port) == 'output')]
    if len(hold) != 1 or len(drivers) != 1:
        raise RuntimeError('Expected one CDR hold driver')
    name, lut = drivers[0]
    if lut['type'] != 'LUT3' or lut['connections'].get('O') != hold:
        raise RuntimeError('Expected direct LUT3 CDR hold decoder')
    inputs = [lut['connections']['I' + str(i)] for i in range(3)]
    if any(len(bits) != 1 for bits in inputs) or set(bits[0] for bits in inputs) != set(loop):
        raise RuntimeError('CDR decoder must depend on exactly the GTX loopback bits')
    init = int(lut['parameters']['INIT'], 2)
    rows = []
    for mode in range(8):
        values = {bit: (mode >> i) & 1 for i, bit in enumerate(loop)}
        address = sum(values[bits[0]] << i for i, bits in enumerate(inputs))
        actual = (init >> address) & 1
        if actual != int(mode == 1):
            raise RuntimeError('Incorrect CDR hold for loopback mode ' + str(mode))
        rows.append(dict(loopback=format(mode, '03b'), cdr_hold=actual))
    return dict(result='PASS', hardware_access=False, qualification=False,
                scope=('packed connectivity via original pin metadata; not bit-level or hardware proof' if routed else 'synthesized logical connectivity; not physical routing or hardware proof'),
                input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                decoder=name, truth_table=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--routed', action='store_true')
    args = parser.parse_args()
    result = check(args.netlist, routed=args.routed)
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')
