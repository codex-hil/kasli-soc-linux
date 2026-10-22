#!/usr/bin/env python3
"""Install locked tool archives into a fresh directory, preserving existing installs."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True,
                        help='Directory containing openxc7.tgz and oss-cad-suite.tgz')
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    assets = json.loads((ROOT / 'toolchains.lock.json').read_text())
    destination = args.destination.resolve()
    if destination.exists():
        parser.error('Destination exists; refusing to reuse or overwrite it')
    verified = {}
    # Verify every archive before creating the destination or extracting anything.
    for name, entry in assets.items():
        archive = args.archives / (name + '.tgz')
        with archive.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != entry['sha256']:
            raise RuntimeError('Archive SHA256 mismatch: ' + name)
        verified[name] = dict(sha256=actual, bytes=archive.stat().st_size,
                              url=entry['url'])
    destination.mkdir(parents=True)
    for name, entry in assets.items():
        target = destination / name if name == 'openxc7' else destination
        target.mkdir(exist_ok=True)
        with tarfile.open(args.archives / (name + '.tgz')) as archive:
            archive.extractall(target, filter='data')
        (destination / name / '.sha256').write_text(entry['sha256'] + '\n')
    for relative in ['openxc7/bin/fasm2frames', 'openxc7/bin/xc7frames2bit',
                     'oss-cad-suite/bin/yosys']:
        if not (destination / relative).is_file():
            raise RuntimeError('Archive layout mismatch: ' + relative)
    report = dict(result='EXTRACTED_NOT_EXECUTION_TESTED', hardware_access=False,
                  destination=str(destination), assets=verified)
    (destination / 'installation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
