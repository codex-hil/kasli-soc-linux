#!/usr/bin/env python3
"""Validate BOOT.BIN partition headers using the same selection rules as SZL."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image", type=Path)
    p.add_argument("--uboot", type=Path, required=True)
    args = p.parse_args()
    blob = args.image.read_bytes()
    word = lambda offset: struct.unpack_from("<I", blob, offset)[0]
    if word(0x20) != 0xaa995566 or word(0x24) != 0x584c4e58:
        raise RuntimeError("invalid BootROM signature")
    fsbl = word(0x30) // 4
    start = word(0x9c)
    partitions = []
    for i in range(3):
        header = struct.unpack_from("<16I", blob, start + 64 * i)
        if sum(header) & 0xffffffff != 0xffffffff:
            raise RuntimeError("partition header checksum mismatch")
        encrypted, length, words, load, entry, data, flags = header[:7]
        if encrypted != length or length != words or (data + length) * 4 > len(blob):
            raise RuntimeError("invalid partition length")
        partitions.append({"length": length * 4, "load": load, "entry": entry,
                           "offset": data * 4, "flags": flags, "bootloader": data == fsbl})
    pl = [p for p in partitions if p["flags"] & 0x20 and not p["bootloader"]]
    ps = [p for p in partitions if p["flags"] & 0x10 and not p["bootloader"]]
    if len(pl) != 1 or len(ps) != 1 or ps[0]["load"] != 0x00100000:
        raise RuntimeError("SZL must find one PL and one PS payload at 0x00100000")
    payload = blob[ps[0]["offset"]:ps[0]["offset"] + ps[0]["length"]]
    expected = args.uboot.read_bytes()
    if payload[:len(expected)] != expected or any(payload[len(expected):]):
        raise RuntimeError("PS payload differs from u-boot.bin")
    print(json.dumps({"result": "PASS", "hardware": False,
                      "boot_bin_sha256": hashlib.sha256(blob).hexdigest(),
                      "partitions": partitions}, indent=2))


if __name__ == "__main__":
    main()
