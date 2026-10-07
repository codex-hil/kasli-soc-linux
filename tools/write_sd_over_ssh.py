#!/usr/bin/env python3
"""Write and verify an SD image from a RAM-root Linux on the target board.

Requires an explicit SD CID, rejects a disk-backed root and mounted SD
partitions. Operates only on /dev/mmcblk0; never accesses QSPI.
"""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def cid(value):
    if not re.fullmatch(r"[0-9a-fA-F]{32}", value):
        raise argparse.ArgumentTypeError("CID must contain exactly 32 hexadecimal digits")
    return value.lower()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("address", type=ipaddress.ip_address)
    p.add_argument("--cid", required=True, type=cid)
    p.add_argument("--image", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--key", type=Path, default=ROOT / "build/ssh/id_ed25519")
    args = p.parse_args()
    size = args.image.stat().st_size
    if not size or size % 512:
        raise RuntimeError("Image must contain a nonzero whole number of SD sectors")
    with args.image.open("rb") as f:
        expected = hashlib.file_digest(f, "sha256").hexdigest()
    ssh = ["ssh", "-i", str(args.key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "StrictHostKeyChecking=accept-new", "-o",
           f"UserKnownHostsFile={args.key.parent / 'known_hosts'}", f"root@{args.address}"]
    guard = (
        "set -eu; "
        "root_type=$(awk '$2 == \"/\" { print $3 }' /proc/mounts); "
        "case $root_type in rootfs|tmpfs|ramfs) ;; *) echo 'Refusing: root is not in RAM' >&2; exit 1;; esac; "
        "if grep -q '^/dev/mmcblk0' /proc/mounts; then echo 'Refusing: SD is mounted' >&2; exit 1; fi; "
        f"test \"$(cat /sys/class/block/mmcblk0/device/cid)\" = {args.cid}; "
        f"test \"$(cat /sys/class/block/mmcblk0/size)\" -ge {size // 512}; "
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {"hardware": True, "address": str(args.address), "device": "/dev/mmcblk0",
              "cid": args.cid, "bytes": size, "image_sha256": expected,
              "qspi_written": False, "preflight_pass": False,
              "write_completed": False, "readback_verified": False}
    try:
        # Complete the guard before sending any bytes or opening SD for writing.
        subprocess.run(ssh + [guard + "echo SD_WRITE_GUARD_PASS"], check=True)
        result["preflight_pass"] = True
        with args.image.open("rb") as f:
            subprocess.run(ssh + [guard + "dd of=/dev/mmcblk0 bs=1048576; sync"],
                           stdin=f, check=True)
        result["write_completed"] = True
        actual = subprocess.check_output(
            ssh + [guard + f"dd if=/dev/mmcblk0 bs=512 count={size // 512} | sha256sum"],
            text=True).split()[0]
        result["readback_sha256"] = actual
        if actual != expected:
            raise RuntimeError("Full SD readback SHA-256 differs from image")
        result["readback_verified"] = True
        print("PASS: full SD image readback SHA-256 " + actual, flush=True)
    finally:
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
