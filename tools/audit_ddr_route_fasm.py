#!/usr/bin/env python3
"""Compare DDR delay-control routing PIPs with tile database and emitted FASM."""
import argparse
import collections
import json
import re
from pathlib import Path


def audit(directory, database):
    top = json.loads((directory / 'top_routed.json').read_text())['modules']['top']
    grid = json.loads((database / 'xc7z045/tilegrid.json').read_text())
    xy = {(v['grid_x'], v['grid_y']): (k, v['type']) for k, v in grid.items()}
    features = set((directory / 'top.fasm').read_text().splitlines())
    nets = {}
    for name, net in top['netnames'].items():
        if len(net['bits']) == 1:
            nets.setdefault(net['bits'][0], []).append((name, net))
    bits = set()
    for name, cell in top['cells'].items():
        if cell['type'].startswith(('IDELAYE2_', 'ODELAYE2_')) and not name.startswith(('adc_rx.', 'adc2_rx.')):
            for port in ('C', 'CE', 'LD'):
                bits.update(cell['connections'][port])
    # Include all data, strobe, serialization and delay nets of failing byte 4.
    lane_sites = set()
    for name, cell in top['cells'].items():
        if re.match(r'IOBUF_(3[2-9])\$', name) or name.startswith('IOBUFDS_4$'):
            site = cell['attributes']['NEXTPNR_BEL'].split('/')[0]
            lane_sites.add(re.search(r'X\d+Y\d+$', site)[0])
    if len(lane_sites) != 10:
        raise ValueError('Expected eight DQ and two DQS I/O sites for byte 4')
    lane_cell_count = 0
    for cell in top['cells'].values():
        site = cell['attributes'].get('NEXTPNR_BEL', '').split('/')[0]
        coord = re.search(r'X\d+Y\d+$', site)
        if coord and coord[0] in lane_sites and cell['type'].startswith(('IDELAY', 'ODELAY', 'ISERDES', 'OSERDES', 'IOB18')):
            lane_cell_count += 1
            for connections in cell['connections'].values():
                bits.update(connections)
    pips = set()
    for bit in bits:
        for _, net in nets.get(bit, []):
            fields = net['attributes'].get('ROUTING', '').split(';')
            pips.update(p for p in fields[1::3] if p)
    cache = {}
    pseudo_features = {}
    counts = collections.Counter()
    exceptions = []
    emitted_examples = []
    for pip in sorted(pips):
        match = re.fullmatch(r'X(\d+)Y(\d+)/([^/]+)/([^/]+)', pip)
        if not match:
            counts['unrecognized_name'] += 1
            exceptions.append(dict(pip=pip, status='unrecognized_name'))
            continue
        x, y, dst, src = match.groups()
        tile, kind = xy[int(x), int(y)]
        if kind not in cache:
            data = json.loads((database / ('tile_type_' + kind + '.json')).read_text())
            cache[kind] = {(v['dst_wire'], v['src_wire']): v for v in data['pips'].values()}
            ppips = database / ('ppips_' + kind.lower() + '.db')
            pseudo_features[kind] = dict(line.split() for line in ppips.read_text().splitlines()) if ppips.exists() else {}
        entry = cache[kind].get((dst, src))
        feature = tile + '.' + dst + '.' + src
        if entry is None:
            # Site-internal and site-boundary edges are represented by nextpnr,
            # but are not tile PIPs. Do not silently count them as verified.
            status = 'not_tile_pip'
        elif kind + '.' + dst + '.' + src in pseudo_features[kind]:
            status = 'database_ppip_' + pseudo_features[kind][kind + '.' + dst + '.' + src]
        elif entry['is_pseudo'] == '1':
            status = 'pseudo_pip'
        elif feature in features:
            status = 'emitted_real_pip'
        else:
            status = 'missing_real_pip'
        counts[status] += 1
        if status == "emitted_real_pip" and len(emitted_examples) < 12:
            emitted_examples.append(feature)
        if status in ('missing_real_pip', 'not_tile_pip'):
            exceptions.append(dict(pip=pip, feature=feature, tile_type=kind, status=status))
    return dict(hardware_access=False, qualification=False, selected_net_bits=len(bits),
                unique_pips=len(pips), lane4_cell_count=lane_cell_count,
                lane4_site_coordinates=sorted(lane_sites), counts=dict(counts),
                emitted_real_pip_examples=emitted_examples, exceptions=exceptions)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gateware', type=Path, required=True)
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = audit(a.gateware, a.database)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['counts']))
    return bool(report['counts'].get('missing_real_pip') or report['counts'].get('unrecognized_name'))


if __name__ == '__main__':
    raise SystemExit(main())
