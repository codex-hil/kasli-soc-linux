#!/usr/bin/env python3
"""Build an isolated XC7Z045 chipdb with the missing, verified HR package pins."""
import csv
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def prepare(openxc7, source_binary=None, build=None, extra_rows=(), grid_path=None):
    original = openxc7/'share/nextpnr/external/prjxray-db/zynq7'
    build = build or ROOT/'build/zc706-adc/chipdb'
    build.mkdir(parents=True, exist_ok=True)
    patch = ROOT/'patches/xc7z045-ffg900-missing-hr.csv'
    provenance = json.loads((patch.with_suffix('.json')).read_text())
    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    if extra_rows:
        digest = hashlib.sha256((digest+json.dumps(list(extra_rows), sort_keys=True)).encode()).hexdigest()
    if grid_path is not None:
        digest = hashlib.sha256((digest+hashlib.sha256(grid_path.read_bytes()).hexdigest()).encode()).hexdigest()
    binary = build/'chipdb-xc7z045.bin'
    marker = build/'manifest.json'
    # Fail closed if the toolchain database differs from the audited artifact.
    source_csv = original/'xc7z045ffg900-2/package_pins.csv'
    if hashlib.sha256(source_csv.read_bytes()).hexdigest() != provenance['original_csv_sha256']:
        raise RuntimeError('XC7Z045 package database changed; re-audit the HR patch')
    source_binary = source_binary or openxc7/'share/nextpnr/himbaechel/xilinx/chipdb-xc7z045.bin'
    original_data = source_binary.read_bytes()
    source_digest = hashlib.sha256(original_data).hexdigest()
    if binary.exists() and marker.exists():
        cached = json.loads(marker.read_text())
        if (cached.get('patch_sha256') == digest
                and cached.get('source_chipdb_sha256') == source_digest
                and cached.get('overlay_version') == 1
                and hashlib.sha256(binary.read_bytes()).hexdigest() == cached.get('chipdb_sha256')):
            return binary
    grid = json.loads((grid_path or original/'xc7z045/tilegrid.json').read_text())
    additions = list(csv.DictReader(patch.open())) + list(extra_rows)
    for row in additions:
        if row['site'] not in grid[row['tile']]['sites']:
            raise RuntimeError('Patched pad does not exist in XC7Z045 tilegrid')
    overlay = build/'zynq7'
    overlay.mkdir(exist_ok=True)
    patched_parts = {f'xc7z045ffg900-{speed}' for speed in (1, 2, 3)}
    for source in original.iterdir():
        dest = overlay/source.name
        if source.name not in patched_parts:
            if not dest.exists():
                dest.symlink_to(source)
            continue
        dest.mkdir(exist_ok=True)
        for file in source.iterdir():
            target = dest/file.name
            if file.name != 'package_pins.csv':
                if not target.exists():
                    target.symlink_to(file)
                continue
            rows = list(csv.DictReader(file.open()))
            pads = {r['pin'] for r in rows}
            if any(r['pin'] in pads for r in additions):
                raise RuntimeError('Patch overlaps existing package pins')
            with target.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader(); writer.writerows(rows+additions)
    # The routing database already contains these sites. Append only package
    # pads and string IDs to the pinned binary (himbaechel schema version 6).
    # This avoids the >10 GiB peak of rebuilding the whole fabric in Python.
    data = bytearray(original_data)
    modified_fields = []
    u32 = lambda pos: struct.unpack_from('<I', data, pos)[0]
    rel = lambda pos: pos + struct.unpack_from('<i', data, pos)[0]
    def string(pos):
        ptr = rel(pos)
        return bytes(data[ptr:data.index(0, ptr)]).decode()
    def set_rel(pos, target):
        struct.pack_into('<i', data, pos, target-pos)
    root = rel(0)
    if (u32(root), u32(root+4)) != (0x00ca7ca7, 6):
        raise RuntimeError('Unexpected chipdb schema')
    const = rel(root+76)
    known, old_count = u32(const), u32(const+8)
    strings = rel(const+4)
    names = [string(strings+4*i) for i in range(old_count)]
    known_names = [''] + [line.strip()[2:-1].strip() for line in
        (ROOT/'upstream/nextpnr/himbaechel/uarch/xilinx/constids.inc').read_text().splitlines()
        if line.strip().startswith('X(')]
    if len(known_names) != known:
        raise RuntimeError('Const ID schema differs from pinned nextpnr')
    ids = {name: i for i, name in enumerate(known_names+names)}
    all_names = dict(enumerate(known_names+names))
    def intern(name):
        if name not in ids:
            ids[name] = known+len(names)
            names.append(name)
        return ids[name]
    def pad(row):
        tile = grid[row['tile']]
        site = row['site']
        prefix, xy = site.rsplit('_', 1)
        x, y = map(int, xy[1:].split('Y'))
        peers = [name for name in tile['sites'] if name.startswith(prefix+'_')]
        coords = [tuple(map(int, name.rsplit('_', 1)[1][1:].split('Y'))) for name in peers]
        relative = f"{prefix}_X{x-min(a for a, b in coords)}Y{y-min(b for a, b in coords)}"
        return (intern(row['pin']), intern(f"X{tile['grid_x']}Y{tile['grid_y']}"),
            intern(f"{relative}.{tile['sites'][site]}.PAD"), 0, 0, 0, 0)
    packages = rel(root+60)
    original_rows = list(csv.DictReader(source_csv.open()))
    patched = 0
    for i in range(u32(root+64)):
        package = packages+16*i
        package_name = all_names[u32(package)]
        if package_name != 'ffg900':
            continue
        old_pads = rel(package+4)
        count = u32(package+8)
        existing = [struct.unpack_from('<7I', data, old_pads+28*j) for j in range(count)]
        expected = {row['pin']: pad(row) for row in original_rows if row['site'].startswith('IOB_')}
        actual = {all_names[entry[0]]: entry for entry in existing}
        if len(original_rows) != len(actual) or any(expected[pin] != actual.get(pin) for pin in expected):
            raise RuntimeError('Pin-to-BEL reconstruction differs: '+str([(pin, exp, actual.get(pin)) for pin, exp in expected.items() if exp != actual.get(pin)][:3]))
        added = [pad(row) for row in additions]
        while len(data) % 4:
            data.append(0)
        new_pads = len(data)
        for entry in existing+added:
            if entry[-1] != 0:
                raise RuntimeError('Unexpected relative extra data on package pad')
            data.extend(struct.pack('<7I', *entry))
        set_rel(package+4, new_pads)
        struct.pack_into('<I', data, package+8, count+len(added))
        modified_fields += [package+4, package+8]
        patched += 1
    if patched != 1:
        raise RuntimeError('Expected exactly one FFG900 package')
    # Existing string IDs remain unchanged. Only the string pointer slice moves.
    while len(data) % 4:
        data.append(0)
    new_strings = len(data)
    data.extend(bytes(4*len(names)))
    for i, name in enumerate(names):
        target = len(data)
        data.extend(name.encode()+b'\0')
        set_rel(new_strings+4*i, target)
    set_rel(const+4, new_strings)
    struct.pack_into('<I', data, const+8, len(names))
    modified_fields += [const+4, const+8]
    restored = bytearray(data[:len(original_data)])
    for field in modified_fields:
        restored[field:field+4] = original_data[field:field+4]
    if restored != original_data:
        raise RuntimeError('Package overlay changed fabric/routing bytes')
    temporary = binary.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(binary)
    marker.write_text(json.dumps({'patch_sha256': digest,
        'chipdb_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'added_hr_pins': len(additions), 'source_chipdb_sha256': source_digest,
        'overlay_version': 1, 'unchanged_fabric_bytes_verified': True,
        'method': 'schema-6 package-only append; existing FFG900 IOB pads verified',
        'provenance': provenance}, indent=2)+'\n')
    return binary
