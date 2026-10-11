#!/usr/bin/env python3
"""Compare lane-four bitslip counter clock/enable/set logic and FF modes."""
import argparse
import json
import re
from pathlib import Path
from compare_ddr_control_logic import Design, compare, evaluate, leaves


def inspect(path, database):
    design = Design(path)
    grid = json.loads((database / 'xc7z045/tilegrid.json').read_text())
    sites = {site: (tile, data['sites'][site]) for tile, data in grid.items() for site in data['sites']}
    features = set((path.parent / 'top.fasm').read_text().splitlines())
    controls, registers, encoding_errors = {}, {}, []
    for dq in range(32, 40):
        for direction in range(2):
            for bit in range(3):
                signal = f'k7ddrphy_bitslip{dq}_value{direction}[{bit}]'
                matches = [net for name, net in design.top['netnames'].items()
                           if name.removeprefix('integratedsoc_') == signal]
                if len(matches) != 1:
                    raise ValueError('Expected counter state ' + signal)
                source, = matches[0]['bits']
                driver, = design.drivers[source]
                name, output = driver
                cell = design.top['cells'][name]
                if cell['type'] != 'SLICE_FFX' or output != 'Q':
                    raise ValueError('Expected counter FF: ' + signal)
                registers[signal] = dict(parameters=cell['parameters'],
                    original_type=cell['attributes']['X_ORIG_TYPE'],
                    synchronous=cell['attributes']['X_FFSYNC'].strip())
                site, bel = cell['attributes']['NEXTPNR_BEL'].split('/')
                tile, kind = sites[site]
                x = int(re.search(r'X(\d+)Y', site)[1])
                prefix = f'{tile}.{kind}_X{x % 2}'
                original_type = cell['attributes']['X_ORIG_TYPE']
                if original_type not in ('FDSE', 'FDRE'):
                    raise ValueError('Unsupported bitslip FF mode: ' + original_type)
                expected = {
                    prefix + '.' + bel + '.ZINI': int(cell['parameters']['INIT'], 2) == 0,
                    prefix + '.' + bel + '.ZRST': original_type == 'FDRE',
                    prefix + '.FFSYNC': True,
                    prefix + '.CLKINV': False,
                    prefix + '.NOCLKINV': True,
                }
                for port, feature in [('CE', 'CEUSEDMUX'), ('SR', 'SRUSEDMUX')]:
                    wire, = cell['connections'][port]
                    cone = design.cone(wire)
                    inactive = ('constant', 1 if port == 'CE' else 0)
                    expected[prefix + '.' + feature] = cone != inactive
                for feature, value in expected.items():
                    if (feature in features) != value:
                        encoding_errors.append(dict(signal=signal, feature=feature,
                                                    expected=value, present=feature in features))
                for port in ('CK', 'CE', 'SR', 'D'):
                    wire, = cell['connections'][port]
                    controls[signal + ':' + port] = design.cone(wire)
    return controls, registers, encoding_errors


def check_increment(controls):
    failures = []
    cases = 0
    for dq in range(32, 40):
        for direction in range(2):
            signals = [f'k7ddrphy_bitslip{dq}_value{direction}[{bit}]' for bit in range(3)]
            expressions = [controls[signal + ':D'] for signal in signals]
            if not set().union(*(leaves(expr) for expr in expressions)) <= set(signals):
                raise ValueError('Counter update has unexpected input boundaries')
            for state in range(8):
                values = {signal: (state >> bit) & 1 for bit, signal in enumerate(signals)}
                got = sum(evaluate(expr, values) << bit for bit, expr in enumerate(expressions))
                cases += 1
                if got != (state + 1) % 8:
                    failures.append(dict(dq=dq, direction=direction, state=state, got=got))
    return dict(cases=cases, failures=failures)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--golden', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    left, lr, le = inspect(a.golden, a.database)
    right, rr, re_errors = inspect(a.candidate, a.database)
    report = compare(left, right)
    report['increment_check'] = dict(golden=check_increment(left), candidate=check_increment(right))
    report['ff_encoding_errors'] = dict(golden=le, candidate=re_errors)
    report['counter_ff_count'] = len(lr)
    report['ff_mode_differences'] = {name: dict(golden=lr[name], candidate=rr[name])
                                    for name in lr if lr[name] != rr[name]}
    report['limitation'] += ' Assembled bits and physical pulse delivery are not checked.'
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print('Counter FFs:',len(lr),'control mismatches:',report['mismatched_sinks'],
          'mode differences:',len(report['ff_mode_differences']), 'FF encoding errors:',len(le)+len(re_errors))
    return bool(report['mismatched_sinks'] or report['ff_mode_differences'] or le or re_errors or any(x['failures'] for x in report['increment_check'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
