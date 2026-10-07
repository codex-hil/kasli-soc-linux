#!/usr/bin/env python3
"""Read-only SLCR/DDRC dump; skips FIFO/status registers with side effects."""
import argparse
import json
import ipaddress
import mmap
import os
from pathlib import Path
import struct
import subprocess

SLCR = [0x100, 0x104, 0x108, 0x10c, 0x110, 0x114, 0x118,
        0x120, 0x124, 0x128, 0x12c, 0x138, 0x140, 0x150, 0x154,
        0x170, 0x180, 0x190, 0x1a0, 0x240, 0x900]
SLCR += list(range(0x700, 0x7d8, 4))
DDRC = [0x0, 0x4, 0x8, 0xc, 0x10, 0x14, 0x18, 0x1c,
        0x20, 0x24, 0x28, 0x2c, 0x30, 0x34, 0x38, 0x3c,
        0x40, 0x44, 0x48, 0x4c, 0x50, 0x54, 0x58, 0x5c,
        0x60, 0x64, 0x68, 0x6c, 0x78, 0xa0, 0xa4, 0xa8, 0xac]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--compare", help="previous JSON dump")
    p.add_argument("--ssh-address", type=ipaddress.ip_address,
                   help="read through BusyBox devmem on a reference Linux without Python")
    p.add_argument("--key", type=Path,
                   default=Path(__file__).resolve().parents[1] / "build/ssh/id_ed25519")
    args = p.parse_args()
    result = {}
    regions = [(0xf8000000, SLCR), (0xf8006000, DDRC)]
    if args.ssh_address:
        addresses = [base + offset for base, offsets in regions for offset in offsets]
        script = "set -e; for a in " + " ".join(f"0x{a:08x}" for a in addresses)
        script += '; do printf "%s " "$a"; devmem "$a"; done'
        output = subprocess.check_output([
            "ssh", "-i", str(args.key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new", "-o",
            f"UserKnownHostsFile={args.key.parent / 'known_hosts'}",
            f"root@{args.ssh_address}", script], text=True, timeout=60)
        for line in output.splitlines():
            address, value = line.split()
            result[f"{int(address, 16):08x}"] = f"{int(value, 16):08x}"
        if set(result) != {f"{a:08x}" for a in addresses}:
            raise RuntimeError("Incomplete register dump")
    else:
        fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
        for base, offsets in regions:
            with mmap.mmap(fd, 4096, flags=mmap.MAP_SHARED,
                           prot=mmap.PROT_READ, offset=base) as mem:
                for offset in offsets:
                    result[f"{base + offset:08x}"] = f"{struct.unpack_from('<I', mem, offset)[0]:08x}"
        os.close(fd)
    if args.compare:
        previous = json.load(open(args.compare))
        result = {k: {"before": previous.get(k), "after": v}
                  for k, v in result.items() if previous.get(k) != v}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
