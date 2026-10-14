#!/usr/bin/env python3
"""Convert physical-site BELs to native tile-local names for offline replay."""
import argparse
import csv
import hashlib
import json
import re
import struct
import mmap
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',type=Path,required=True)
p.add_argument('--tilegrid',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--package',type=Path,required=True)
p.add_argument('--chipdb',type=Path,required=True)
p.add_argument('--logical-lut-inputs',action='store_true',help='Experimental: retain only original mapped LUT A inputs')
p.add_argument('--prerouted',type=Path,help='Also normalize SITEWIRE names in a reference preroute file')
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
chipfile=a.chipdb.open('rb')
data=mmap.mmap(chipfile.fileno(),0,access=mmap.ACCESS_READ)
u32=lambda pos:struct.unpack_from('<I',data,pos)[0]
rel=lambda pos:pos+struct.unpack_from('<i',data,pos)[0]
root=rel(0)
if (u32(root),u32(root+4))!=(0x00ca7ca7,6):raise ValueError('Unsupported chipdb schema')
const=rel(root+76);known=u32(const);strings=rel(const+4)
constids=Path(__file__).resolve().parents[1]/'upstream/nextpnr/himbaechel/uarch/xilinx/constids.inc'
names=['']+[line.strip()[2:-1].strip() for line in constids.read_text().splitlines() if line.strip().startswith('X(')]
if len(names)!=known:raise ValueError('Const ID mismatch')
for i in range(u32(const+8)):
    ptr=rel(strings+4*i);names.append(data[ptr:data.find(b'\0',ptr)].decode())
types=rel(root+28);tiles=rel(root+36);tile_names={}
for i in range(u32(root+40)):
    pos=tiles+16*i;width=u32(root+8)
    tile_names[f'{names[u32(pos)]}X{i%width}Y{i//width}']=u32(pos+4)
cache={}
def bel_names(tile):
    index=tile_names[tile]
    if index not in cache:
        pos=types+40*index;ptr=rel(pos+4)
        cache[index]={names[u32(ptr+36*i)] for i in range(u32(pos+8))}
    return cache[index]
design=json.loads(a.input.read_text());module=design['modules']['top'];count=0
for name,cell in module['cells'].items():
    bel=cell['attributes'].get('NEXTPNR_BEL')
    if not bel:raise ValueError('Unplaced cell '+name)
    site,kind=bel.split('/')
    if site == 'X0Y0' and kind in ('PSEUDO_VCC','PSEUDO_GND'):
        continue
    if site not in sites:raise ValueError('Unknown site '+site)
    tile,local=sites[site].split('/')
    local += '.'+kind
    local_names=bel_names(tile)
    if local not in local_names:
        variants=sorted(n for n in local_names if n.startswith(local+'~'))
        if len(variants)!=1:raise ValueError('Missing/ambiguous native BEL '+local)
        local=variants[0]
    cell['attributes']['NEXTPNR_BEL']=tile+'/'+local;count+=1
constant_bits={bit for name,net in module['netnames'].items() if name in ('$PACKER_GND_NET','$PACKER_VCC_NET') for bit in net['bits']}
removed_lut_inputs=0;preserved_constant_inputs=0
if a.logical_lut_inputs:
    for cell in module['cells'].values():
        if cell['type']!='SLICE_LUTX':continue
        keep={k.removeprefix('X_ORIG_PORT_') for k in cell['attributes'] if k.startswith('X_ORIG_PORT_')}
        if not keep:raise ValueError('LUT lacks original port mapping')
        for port in list(cell['connections']):
            if port in ('A1','A2','A3','A4','A5','A6') and port not in keep:
                if cell['connections'][port] and all(bit in constant_bits for bit in cell['connections'][port]):
                    preserved_constant_inputs+=1;continue
                del cell['connections'][port];cell['port_directions'].pop(port,None)
                removed_lut_inputs+=1
# Route names are also exported physically; replay placement only, reroute later.
for net in module['netnames'].values():net['attributes'].pop('ROUTING',None)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(design)+'\n')
report={'hardware_access':False,'qualification':False,'converted_cells':count,'removed_lut_inputs':removed_lut_inputs,'preserved_constant_inputs':preserved_constant_inputs,'removed_existing_routes':True,
        'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),
        'chipdb_sha256':hashlib.sha256(data).hexdigest(),
        'package_sha256':hashlib.sha256(a.package.read_bytes()).hexdigest(),
        'tilegrid_sha256':hashlib.sha256(a.tilegrid.read_bytes()).hexdigest(),
        'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}
a.output.with_suffix('.summary.json').write_text(json.dumps(report,indent=2)+'\n');print(report)

if a.prerouted:
    rows=[]
    for line in a.prerouted.read_text().splitlines():
        name,route=line.split('\t',1);fields=route.split(';')
        for i in range(0,len(fields)-2,3):
            if fields[i].startswith('SITEWIRE/'):
                _,site,pin=fields[i].split('/')
                if site not in sites:raise ValueError('Unknown reference wire site '+site)
                fields[i]=sites[site]+'.'+pin
        rows.append(name+'\t'+';'.join(fields))
    a.output.with_suffix('.prerouted.txt').write_text('\n'.join(rows)+'\n')
