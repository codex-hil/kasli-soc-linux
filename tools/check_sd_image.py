#!/usr/bin/env python3
"""Audit generated MBR partitions against their source filesystem images."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def audit(image):
    checks = []
    with image.open('rb') as stream:
        mbr = stream.read(512)
        if len(mbr) != 512 or mbr[510:] != b'\x55\xaa':
            raise RuntimeError('invalid MBR signature')
        previous_end = 1
        for index, name, expected_type in [(0, 'boot.vfat', 12), (1, 'rootfs.ext4', 131)]:
            entry = mbr[446 + 16 * index:462 + 16 * index]
            kind = entry[4]
            start, count = struct.unpack_from('<II', entry, 8)
            source = image.parent / name
            if kind != expected_type or start < previous_end or count == 0:
                raise RuntimeError(f'invalid partition {index + 1}')
            previous_end = start + count
            if previous_end * 512 > image.stat().st_size or source.stat().st_size > count * 512:
                raise RuntimeError('partition exceeds image bounds')
            stream.seek(start * 512)
            with source.open('rb') as payload:
                while block := payload.read(1024 * 1024):
                    if stream.read(len(block)) != block:
                        raise RuntimeError(f'partition {index + 1} differs from {name}')
            checks.append(dict(partition=index + 1, type=kind, start_sector=start,
                               sectors=count, payload_identical=True))
    with image.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(hardware_validated=False, checks=checks, image_sha256=digest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.image), indent=2))
