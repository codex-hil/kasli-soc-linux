#!/usr/bin/env python3
"""Map each bonded PL I/O pin to its differential pair and termination bits.

Package/site geometry is not a physical validation of every pin. HR feature
bits are measured separately; HP and unpaired pins are explicitly excluded.
"""
import argparse
import csv
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--part', default='xc7z045ffg900-2')
    p.add_argument('--db', type=Path, default=ROOT/'build/tools/openxc7/share/nextpnr/external/prjxray-db/zynq7')
    p.add_argument('--output', type=Path, default=ROOT/'build/zc706-adc/termination-reference/zc706-pins.csv')
    a = p.parse_args()
    die = re.match(r'(xc7z\d+)', a.part)[1]
    grid = json.loads((a.db/die/'tilegrid.json').read_text())
    mapping = json.loads((ROOT/'patches/prjxray-hr-diff-term.json').read_text())
    rows = list(csv.DictReader((a.db/a.part/'package_pins.csv').open()))
    if a.part == 'xc7z045ffg900-2':
        rows += list(csv.DictReader((ROOT/'patches/xc7z045-ffg900-missing-hr.csv').open()))
    by_pin = {}
    for row in rows:
        if row['pin'] in by_pin and by_pin[row['pin']] != row:
            raise ValueError('Conflicting package mapping: '+row['pin'])
        by_pin[row['pin']] = row
    by_site = {r['site']: r for r in by_pin.values()}
    records = []
    for row in sorted(by_pin.values(), key=lambda r: (int(r['bank']), r['site'])):
        tile = grid[row['tile']]
        kind = tile['type']
        status, pair_pin, polarity, coords = ('unpaired' if row['site'].startswith('IOB_')
                                            else 'not PL I/O'), '', '', []
        if kind in ('LIOB33', 'RIOB33', 'LIOB18', 'RIOB18'):
            y = int(row['site'].split('Y')[-1])
            polarity = 'P' if y % 2 == 0 else 'N'
            partner = by_site.get(row['site'].split('Y')[0]+'Y'+str(y-1 if y%2 == 0 else y+1))
            if partner and partner['tile'] == row['tile']:
                pair_pin = partner['pin']
                status = 'HP: not measured' if 'IOB18' in kind else 'HR: measured tile feature; package geometry'
                if 'IOB33' in kind:
                    region = tile['bits']['CLB_IO_CLK']
                    for value in mapping['features'][kind+'.DIFF.DIFF_TERM']:
                        if value.startswith('!'):
                            raise ValueError('Expected positive termination bits')
                        frame, bit = map(int, value.split('_'))
                        if frame >= region['frames'] or bit >= region['words']*32:
                            raise ValueError('Termination bit outside tile')
                        coords.append('bit_%08x_%03d_%02d' % (
                            int(region['baseaddr'], 16)+frame, region['offset']+bit//32, bit%32))
        records.append(dict(**row, tile_type=kind, polarity=polarity,
                            partner_pin=pair_pin, status=status,
                            termination_bits=' '.join(coords)))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('w') as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader(); writer.writerows(records)
    print(json.dumps(dict(part=a.part, package_signal_pins=len(records),
        pl_io_pins=sum(r['site'].startswith('IOB_') for r in records),
        hr_pair_pins=sum(bool(r['termination_bits']) for r in records),
        hp_pair_pins=sum(r['status'].startswith('HP') for r in records),
        unpaired_pins=sum(r['status']=='unpaired' for r in records),
        output=str(a.output)), indent=2))


if __name__ == '__main__':
    main()
