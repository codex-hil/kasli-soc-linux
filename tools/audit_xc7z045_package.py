#!/usr/bin/env python
"""Optional independent package audit, run under RapidWright's Jython.

java -Xmx2g -jar rapidwright.jar tools/audit_xc7z045_package.py \
    original-package.csv patches/xc7z045-ffg900-missing-hr.csv audit.json

Not a gateware build dependency; does not invoke Vivado or access hardware.
"""
import csv
import hashlib
import json
import sys
from com.xilinx.rapidwright.device import Device


def main():
    original, patch, output = sys.argv[1:]
    device = Device.getDevice('xc7z045ffg900-2')
    package = device.getActivePackage()
    result = {'part': 'xc7z045ffg900-2', 'package': package.getName(),
              'hardware_test': False, 'sources': [], 'pins': [], 'errors': []}
    for source in (original, patch):
        with open(source, 'rb') as f:
            result['sources'].append({'path': source, 'sha256': hashlib.sha256(f.read()).hexdigest()})
        with open(source) as f:
            for row in csv.DictReader(f):
                if not row['site'].startswith('IOB_'):
                    continue
                pin = package.getPackagePin(row['pin'])
                site = pin.getSite() if pin is not None else None
                actual_site = str(site) if site is not None else None
                actual_tile = str(site.getTile()) if site is not None else None
                match = actual_site == row['site'] and actual_tile == row['tile']
                record = {'pin': row['pin'], 'expected_site': row['site'],
                          'expected_tile': row['tile'], 'actual_site': actual_site,
                          'actual_tile': actual_tile, 'match': match}
                result['pins'].append(record)
                if not match:
                    result['errors'].append(record)
    result['result'] = 'PASS' if not result['errors'] else 'FAIL'
    with open(output, 'w') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print('%s: %d package pin/site/tile mappings, %d errors' %
          (result['result'], len(result['pins']), len(result['errors'])))
    if result['errors']:
        sys.exit(1)


if __name__ == '__main__':
    main()
