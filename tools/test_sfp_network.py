#!/usr/bin/env python3
"""Verify PL MAC/ARP/ICMP and byte-exact UDP echo through an Ethernet switch."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ip", type=ipaddress.IPv4Address, default="192.168.2.206")
    p.add_argument("--port", type=int, default=1234)
    p.add_argument("--repeat", type=int, default=50)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if not 1 <= a.repeat <= 100000:
        p.error("--repeat must be 1..100000")
    result = {"result": "FAIL", "target": str(a.ip), "port": a.port,
        "sizes": [1, 17, 64, 128, 512, 1024, 1400], "repeats": a.repeat,
        "completed_packets": 0, "completed_bytes": 0}
    try:
        ping = subprocess.run(["ping", "-c", "20", "-W", "1", str(a.ip)],
            capture_output=True, text=True, timeout=40)
        result["ping"] = {"returncode": ping.returncode, "stdout": ping.stdout, "stderr": ping.stderr}
        if ping.returncode:
            raise RuntimeError("PL ICMP test failed")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.connect((str(a.ip), a.port))
            start = time.monotonic()
            for shot in range(a.repeat):
                for size in result["sizes"]:
                    seed = f"zc706-sfp:{shot}:{size}".encode()
                    data = hashlib.shake_256(seed).digest(size)
                    sock.send(data)
                    response = sock.recv(2048)
                    if response != data:
                        raise RuntimeError(f"UDP mismatch: shot {shot}, size {size}, received {len(response)}")
                    result["completed_packets"] += 1
                    result["completed_bytes"] += size
            result["elapsed_seconds"] = time.monotonic()-start
        result["result"] = "PASS"
    except Exception as e:
        result["error"] = str(e)
        raise
    finally:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
