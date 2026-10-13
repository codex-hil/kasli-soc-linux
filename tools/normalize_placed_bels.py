#!/usr/bin/env python3
"""Convert physical-site BELs to native tile-local names for offline replay."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',type=Path,required=True)
p.add_argument('--tilegrid',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--package',type=Path,required=True)
a=p.parse_args();grid=json.loads(a.tilegrid.read_text());sites={}
# Package records explicitly locate IOB sites omitted from tilegrid metadata.
for row in csv.DictReader(a.package.open()):
    if row['site'].startswith('IOB_'):
        if row['tile'] not in grid:raise ValueError('Unknown package tile')
        grid[row['tile']]['sites'].setdefault(row['site'], 'package')
for tile in grid.values():
    groups={}
    for site in tile['sites']:
        m=re.fullmatch(r'(.+)_X(\d+)Y(\d+)',site)
        if not m:raise ValueError('Unrecognized site '+site)
        groups.setdefault(m[1],[]).append((site,int(m[2]),int(m[3])))
    for prefix,rows in groups.items():
        minx=min(x for _,x,y in rows);miny=min(y for _,x,y in rows)
        for site,x,y in rows:
            if site in sites:raise ValueError('Duplicate site '+site)
            sites[site]=f"X{tile['grid_x']}Y{tile['grid_y']}/{prefix}_X{x-minx}Y{y-miny}"
design=json.loads(a.input.read_text());module=design['modules']['top'];count=0
for name,cell in module['cells'].items():
    bel=cell['attributes'].get('NEXTPNR_BEL')
    if not bel:raise ValueError('Unplaced cell '+name)
    site,kind=bel.split('/')
    if site == 'X0Y0' and kind in ('PSEUDO_VCC','PSEUDO_GND'):
        continue
    if site not in sites:raise ValueError('Unknown site '+site)
    cell['attributes']['NEXTPNR_BEL']=sites[site]+'.'+kind;count+=1
# Route names are also exported physically; replay placement only, reroute later.
for net in module['netnames'].values():net['attributes'].pop('ROUTING',None)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(design)+'\n')
report={'hardware_access':False,'qualification':False,'converted_cells':count,'removed_existing_routes':True,
        'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),
        'package_sha256':hashlib.sha256(a.package.read_bytes()).hexdigest(),
        'tilegrid_sha256':hashlib.sha256(a.tilegrid.read_bytes()).hexdigest(),
        'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}
a.output.with_suffix('.summary.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
