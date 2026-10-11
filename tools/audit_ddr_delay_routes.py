#!/usr/bin/env python3
"""Audit routed DDR delay control sinks; this is not hardware qualification."""
import argparse
import json
from pathlib import Path


def audit(path):
    module = json.loads(path.read_text())['modules']['top']
    nets = {}
    for name, net in module['netnames'].items():
        if len(net['bits']) == 1:
            nets.setdefault(net['bits'][0], []).append((name, net))
    rows = []
    missing = []
    for name, cell in sorted(module['cells'].items()):
        if not cell['type'].startswith(('IDELAYE2_', 'ODELAYE2_')):
            continue
        if name.startswith(('adc_rx.', 'adc2_rx.')):
            continue
        bel = cell['attributes']['NEXTPNR_BEL']
        site = bel.split('/')[0]
        ports = {}
        for port in ('C', 'CE', 'LD', 'INC', 'LDPIPEEN'):
            bit, = cell['connections'][port]
            aliases = nets.get(bit, [])
            destinations = set()
            for _, net in aliases:
                fields = net['attributes'].get('ROUTING', '').split(';')
                destinations.update(fields[0::3])
            sink = 'SITEWIRE/' + site + '/' + port
            present = sink in destinations
            ports[port] = dict(sink=sink, present=present,
                               net_names=[n for n, _ in aliases])
            if not present:
                missing.append(dict(cell=name, bel=bel, port=port, sink=sink))
        rows.append(dict(cell=name, bel=bel, ports=ports))
    if not rows:
        raise ValueError('No DDR delay cells found')
    return dict(input=str(path), hardware_access=False, qualification=False,
                delay_cell_count=len(rows), missing_sinks=missing, cells=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routed-json', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.routed_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('DDR delay cells:', report['delay_cell_count'],
          'missing control sinks:', len(report['missing_sinks']))
    for row in report['missing_sinks'][:10]:
        print(row)
    return bool(report['missing_sinks'])


if __name__ == '__main__':
    raise SystemExit(main())
