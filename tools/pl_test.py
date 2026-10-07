#!/usr/bin/env python3
"""Hardware test using the generated CSR map. Requires root and loaded PL."""
import argparse
import json
import mmap
import os
import random
import struct
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csr-json", required=True)
    p.add_argument("--device", default="/dev/mem")
    p.add_argument("--iterations", type=int, default=10000)
    args = p.parse_args()
    regs = json.load(open(args.csr_json))["csr_registers"]
    base = regs["probe_scratch"]["addr"] & ~(mmap.PAGESIZE - 1)
    offset = base
    if os.path.basename(args.device).startswith("uio"):
        map_dir = "/sys/class/uio/" + os.path.basename(args.device) + "/maps/map0"
        with open(map_dir + "/addr") as f:
            mapped_base = int(f.read().strip(), 0)
        with open(map_dir + "/size") as f:
            mapped_size = int(f.read().strip(), 0)
        if mapped_base != base or mapped_size < mmap.PAGESIZE:
            raise RuntimeError("UIO map does not cover the expected LiteX CSR page")
        offset = 0  # UIO mmap offset selects map index, not physical address.
    fd = os.open(args.device, os.O_RDWR | os.O_SYNC)
    with mmap.mmap(fd, mmap.PAGESIZE, flags=mmap.MAP_SHARED,
                   prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=offset) as mem:
        def read(name):
            return struct.unpack_from("<I", mem, regs["probe_" + name]["addr"] - base)[0]
        def write(value):
            struct.pack_into("<I", mem, regs["probe_scratch"]["addr"] - base, value)
        if read("signature") != 0x4b534f43:
            raise RuntimeError("PL signature mismatch")
        original = read("scratch")
        try:
            rng = random.Random(0x4b534f43)
            patterns = [0, 0xffffffff, 0xaaaaaaaa, 0x55555555]
            patterns += [1 << bit for bit in range(32)]
            for value in patterns + [rng.getrandbits(32) for _ in range(args.iterations)]:
                write(value)
                actual = read("scratch")
                if actual != value:
                    raise RuntimeError(f"scratch: expected {value:#x}, got {actual:#x}")
            samples = []
            for _ in range(10):
                a = read("counter")
                start = time.monotonic()
                time.sleep(0.02)
                b = read("counter")
                elapsed = time.monotonic() - start
                rate = ((b - a) & 0xffffffff) / elapsed
                if not 90e6 < rate < 110e6:
                    raise RuntimeError(f"counter clock outside 100MHz ±10%: {rate}")
                samples.append(rate)
            print(json.dumps({"hardware": True, "result": "PASS",
                              "writes": len(patterns) + args.iterations,
                              "counter_hz": samples}))
        finally:
            write(original)
    os.close(fd)


if __name__ == "__main__":
    main()
