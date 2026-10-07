#!/usr/bin/env python3
"""Fetch checksum-pinned published HERO ZC706 binaries; optionally make SD image.

Diagnostic comparator only: these are externally generated vendor binaries,
not evidence that our openXC7 design works. Never writes a physical device.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', action='store_true', help='Run in project container')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'configs/zc706-reference.json').read_text())
    output = ROOT / 'build/zc706-vendor-baseline'
    output.mkdir(parents=True, exist_ok=True)
    for name, expected in lock['files'].items():
        path = output / name
        if not path.exists():
            partial = path.with_suffix(path.suffix + '.partial')
            with urllib.request.urlopen(lock['base_url'] + name, timeout=60) as source:
                with partial.open('wb') as target:
                    shutil.copyfileobj(source, target)
            if hashlib.sha256(partial.read_bytes()).hexdigest() != expected:
                partial.unlink()
                raise SystemExit(f'Checksum mismatch: {name}')
            partial.replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Checksum mismatch: {path}')
        print(f'{name}: SHA-256 PASS', flush=True)
    if args.image:
        host = ROOT / 'build/zc706/buildroot/host'
        temporary = output / 'genimage-tmp'
        if temporary.exists():
            shutil.rmtree(temporary)
        empty = output / 'empty-root'
        empty.mkdir(exist_ok=True)
        subprocess.run([str(host / 'bin/genimage'), '--rootpath', str(empty),
                        '--tmppath', str(temporary), '--inputpath', str(output),
                        '--outputpath', str(output), '--config',
                        str(ROOT / 'configs/zc706-reference-genimage.cfg')],
                       check=True, env=dict(os.environ, PATH=f'{host}/bin:{host}/sbin:' + os.environ['PATH']))
        image = output / 'sdcard.img'
        print(f'{image}: SHA-256 {hashlib.sha256(image.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
