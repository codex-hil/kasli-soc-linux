#!/usr/bin/env python3
"""Exhaustively check FASM INIT encoding of DDR delay CE/LD driver LUTs."""
import argparse
import json
import re
from pathlib import Path


def audit(directory, tilegrid):
    top = json.loads((directory / 'top_routed.json').read_text())['modules']['top']
    sites = {site: tile for tile, data in tilegrid.items() for site in data['sites']}
    inits = {}
    for line in (directory / 'top.fasm').read_text().splitlines():
        match = re.fullmatch(r"(.*LUT.INIT)\[63:0\] = 64'b([01]{64})", line)
        if match:
            inits[match[1]] = int(match[2], 2)
    drivers = {}
    for name, cell in top['cells'].items():
        for port, bits in cell['connections'].items():
            if cell['port_directions'][port] == 'output':
                for bit in bits:
                    drivers.setdefault(bit, []).append((name, port))
    selected = set()
    for name, cell in top['cells'].items():
        if cell['type'].startswith(('IDELAYE2_', 'ODELAYE2_')) and not name.startswith(('adc_rx.', 'adc2_rx.')):
            for port in ('CE', 'LD'):
                bit, = cell['connections'][port]
                for driver in drivers.get(bit, []):
                    selected.add(driver)
    results = []
    for name, output in sorted(selected):
        cell = top['cells'][name]
        if cell['type'] != 'SLICE_LUTX':
            raise ValueError('Unexpected control driver: ' + name + ':' + cell['type'])
        site, bel = cell['attributes']['NEXTPNR_BEL'].split('/')
        tile = sites[site]
        site_type = tilegrid[tile]['sites'][site]
        site_x = int(re.search(r'X(\d+)Y', site)[1])
        feature = f'{tile}.{site_type}_X{site_x % 2}.{bel[0]}LUT.INIT'
        actual = inits[feature]
        original = int(cell['parameters']['INIT'], 2)
        inputs = {}
        for port in cell['connections']:
            origin = cell['attributes'].get('X_ORIG_PORT_' + port, '')
            if origin.startswith('I') and origin[1:].isdigit():
                inputs[int(origin[1:])] = int(port[1:]) - 1
        # A shared O6 LUT has A6 tied high; its lower half belongs to O5.
        fixed_pins = {}
        for port, bits in cell['connections'].items():
            if port.startswith('A') and port[1:].isdigit() and len(bits) == 1:
                for driver, _ in drivers.get(bits[0], []):
                    kind = top['cells'][driver]['type']
                    if kind in ('PSEUDO_VCC', 'PSEUDO_GND'):
                        fixed_pins[int(port[1:]) - 1] = int(kind == 'PSEUDO_VCC')
        mismatches = []
        for physical in range(32 if output == 'O5' else 64):
            if any(((physical >> pin) & 1) != value for pin, value in fixed_pins.items()):
                continue
            logical = sum(((physical >> pin) & 1) << index for index, pin in inputs.items())
            expected = (original >> logical) & 1
            emitted = (actual >> physical) & 1
            if expected != emitted:
                mismatches.append(physical)
        results.append(dict(cell=name, output=output, feature=feature,
                            input_mapping=inputs, mismatches=mismatches))
    if not results:
        raise ValueError('No DDR control LUTs checked')
    return dict(hardware_access=False, qualification=False, checked_outputs=len(results),
                mismatched_outputs=sum(bool(r['mismatches']) for r in results), outputs=results)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gateware', type=Path, required=True)
    p.add_argument('--tilegrid', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = audit(a.gateware, json.loads(a.tilegrid.read_text()))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print('Checked outputs:', report['checked_outputs'], 'mismatches:', report['mismatched_outputs'])
    return bool(report['mismatched_outputs'])


if __name__ == '__main__':
    raise SystemExit(main())
