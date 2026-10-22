#!/usr/bin/env python3
"""Strict synthesized GTX PCS admission: exhaustively check CDR hold for all modes."""
import argparse
import hashlib
import json
from pathlib import Path


def check(path):
    path = Path(path)
    top = json.loads(path.read_text())['modules']['top']
    channels = [c for c in top['cells'].values() if c['type'] == 'GTXE2_CHANNEL']
    if len(channels) != 1:
        raise RuntimeError('Expected exactly one GTX channel')
    channel = channels[0]
    for name, expected in [('RXBUF_EN', 'TRUE'), ('RX_XCLK_SEL', 'RXREC')]:
        if channel['parameters'].get(name) != expected:
            raise RuntimeError('Unsupported GTX parameter: ' + name)
    if channel['connections'].get('RXOUTCLKSEL') != ['0', '1', '0']:
        raise RuntimeError('Expected PMA RXOUTCLK selection 010')
    loop = channel['connections']['LOOPBACK']
    hold = channel['connections']['RXCDRHOLD']
    if len(loop) != 3 or len(set(loop)) != 3 or not all(isinstance(b, int) for b in loop):
        raise RuntimeError('Expected three distinct dynamic loopback bits')
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
                scope='synthesized logical connectivity; not physical routing or hardware proof',
                input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                decoder=name, truth_table=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check(args.netlist)
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')
