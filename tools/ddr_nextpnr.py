#!/usr/bin/env python3
"""Build pinned nextpnr with the isolated XC7 I/O search fix."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    out = ROOT/'build/zc706-ddr'
    source = out/'nextpnr-source'
    build = out/'nextpnr-build'
    patch = ROOT/'patches/nextpnr-xc7-io-site-search.patch'
    revision = subprocess.check_output(['git', '-C', ROOT/'upstream/nextpnr',
        'rev-parse', 'HEAD'], text=True).strip()
    identity = {'revision': revision,
        'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest()}
    marker = out/'nextpnr-manifest.json'
    binary = build/'nextpnr-himbaechel-xilinx'
    if marker.exists() and binary.exists():
        cached = json.loads(marker.read_text())
        if all(cached.get(k) == v for k, v in identity.items()) and cached.get('binary_sha256') == hashlib.sha256(binary.read_bytes()).hexdigest():
            return binary
    shutil.copytree(ROOT/'upstream/nextpnr', source, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('.git'))
    subprocess.run(['patch', '-p1', '-i', patch.resolve()], cwd=source, check=True)
    subprocess.run(['cmake', '-S', source, '-B', build, '-DARCH=himbaechel',
        '-DHIMBAECHEL_UARCH=xilinx', '-DHIMBAECHEL_SPLIT=ON',
        '-DHIMBAECHEL_XILINX_DEVICES=', '-DIMPORT_BBA_FILES=ON',
        '-DBUILD_PYTHON=OFF', '-DBUILD_GUI=OFF', '-DCMAKE_BUILD_TYPE=Release'], check=True)
    subprocess.run(['cmake', '--build', build, '-j2'], check=True)
    marker.write_text(json.dumps({**identity,
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}, indent=2)+'\n')
    return binary


if __name__ == '__main__':
    print(prepare())
