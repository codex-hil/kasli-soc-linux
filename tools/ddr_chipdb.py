#!/usr/bin/env python3
"""Generate isolated Zynq HP IO metadata for PL DDR; never edit upstream."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def prepare(openxc7, *, out=None, database=None, extra_sites=()):
    source = ROOT/'upstream/nextpnr/himbaechel'
    out = out or ROOT/'build/zc706-ddr/chipdb'
    out.mkdir(parents=True, exist_ok=True)
    binary = out/'chipdb-xc7z045.bin'
    marker = out/'manifest.json'
    if database is None:
        database = openxc7/'share/nextpnr/external/prjxray-db/zynq7'
    version = 2
    subprocess.run(['git', '-C', ROOT/'upstream/nextpnr', 'submodule', 'update',
        '--init', '--depth', '1', 'himbaechel/uarch/xilinx/meta'], check=True)
    revision = subprocess.check_output(['git', '-C', source.parent,
        'rev-parse', 'HEAD'], text=True).strip()
    metadata_revision = subprocess.check_output(['git', '-C', source/'uarch/xilinx/meta',
        'rev-parse', 'HEAD'], text=True).strip()
    identity = {'nextpnr_revision': revision, 'metadata_revision': metadata_revision,
        'openxc7_build_info_sha256': hashlib.sha256((openxc7/'BUILD-INFO.json').read_bytes()).hexdigest()}
    if extra_sites:
        identity['extra_metadata'] = {name: hashlib.sha256((source/f'uarch/xilinx/meta/kintex7/site_type_{name}.json').read_bytes()).hexdigest() for name in extra_sites}
        identity['tilegrid_sha256'] = hashlib.sha256((database/'xc7z045/tilegrid.json').read_bytes()).hexdigest()
    if binary.exists() and marker.exists():
        cached = json.loads(marker.read_text())
        if (cached.get('version') == version
                and all(cached.get(k) == v for k, v in identity.items())
                and hashlib.sha256(binary.read_bytes()).hexdigest() == cached.get('chipdb_sha256')):
            return binary
    metadata = out/'metadata'
    metadata.mkdir(exist_ok=True)
    for item in (source/'uarch/xilinx/meta/zynq7').iterdir():
        dest = metadata/item.name
        if not dest.exists():
            dest.symlink_to(item)
    # HP banks share these Series-7 primitive definitions with Kintex-7.
    additions = {}
    for name in ('ILOGICE2', 'OLOGICE2', 'ODELAYE2', 'IDELAYE2_FINEDELAY') + tuple(extra_sites):
        original = source/f'uarch/xilinx/meta/kintex7/site_type_{name}.json'
        dest = metadata/original.name
        if dest.is_symlink(): dest.unlink()
        shutil.copyfile(original, dest)
        additions[original.name] = hashlib.sha256(original.read_bytes()).hexdigest()
    generator_root = out/'generator'
    generator_himbaechel = generator_root/'himbaechel'
    shutil.copytree(source/'himbaechel_dbgen', generator_himbaechel/'himbaechel_dbgen', dirs_exist_ok=True)
    gen = generator_himbaechel/'uarch/xilinx/gen'
    shutil.copytree(source/'uarch/xilinx/gen', gen, dirs_exist_ok=True)
    shutil.copyfile(source/'uarch/xilinx/constids.inc', gen.parent/'constids.inc')
    # Node union must be idempotent: merging a node with itself appends to the
    # very list being iterated, grows without bound, and exhausts host memory.
    tc = gen/'tileconn.py'
    text = tc.read_text()
    needle = '    def merge_nodes(a, b):\n'
    if text.count(needle) != 1:
        raise RuntimeError('tileconn node union changed; re-audit patch')
    tc.write_text(text.replace(needle, needle+'        if a is b:\n            return\n'))
    # Slots reduce per-wire graph memory without changing exported data.
    device = gen/'xilinx_device.py'
    text = device.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for cls in reversed([n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ("Wire", "Node")]):
        attrs = sorted({n.attr for n in ast.walk(cls) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == 'self' and isinstance(n.ctx, ast.Store)})
        lines.insert(cls.lineno, '    __slots__ = '+repr(tuple(attrs))+'\n')
    device.write_text(''.join(lines))
    export = gen/'xilinx_gen.py'
    text = export.read_text()
    needle = '                seen_nodes.add(uid)\n'
    if text.count(needle) != 1:
        raise RuntimeError('Node export changed; re-audit streaming release')
    # Once exported, a node only needs its identity for later duplicate visits.
    # Drop its wire list, and drop each tile's lookup after its final visit.
    text = text.replace(needle, needle+'                n.wires.clear()\n            t.wire_to_node.clear()\n')
    export.write_text(text)
    bba = out/'xc7z045.bba'
    command = [sys.executable, '-u', gen/'xilinx_gen.py', '--xray', database,
        '--metadata', metadata, '--device', 'xc7z045', '--bba', bba]
    with (out/'generator.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([openxc7/'bin/bbasm', '-l', bba, binary], check=True)
    marker.write_text(json.dumps({**identity, 'version': version, 'chipdb_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'metadata_additions': additions, 'node_union_self_merge_guard': True,
        'generator_wire_slots': True, 'streaming_graph_release': True,
        'hardware_validated': False}, indent=2)+'\n')
    return binary


if __name__ == '__main__':
    print(prepare((ROOT/'build/tools/openxc7').resolve()))
