#!/usr/bin/env python3
"""Host-side ping/SSH/DDR/PL checks; saves physical evidence, never simulation."""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("address", type=ipaddress.ip_address)
    p.add_argument("--key", type=Path, default=ROOT / "build/ssh/id_ed25519")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {"hardware": True, "address": str(args.address),
              "time": datetime.now(timezone.utc).isoformat(), "checks": {},
              "milestone_1_complete": False}
    ssh = ["ssh", "-i", str(args.key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "StrictHostKeyChecking=accept-new", "-o",
           f"UserKnownHostsFile={args.key.parent / 'known_hosts'}", "root@" + str(args.address)]
    commands = [
        ("ping", ["ping", "-c", "5", str(args.address)], 20),
        ("ssh_diagnostics", ssh + ["uname -a; cat /proc/meminfo; ip addr show eth0; ethtool eth0; dmesg"], 30),
        ("ddr", ssh + ["memtester 128M 3"], 600),
        ("pl", ssh + ["python3 /usr/bin/pl_test.py --csr-json /etc/litex/csr.json --iterations 10000"], 60),
        ("ps7_dump", ssh + ["python3 /usr/bin/dump_ps7_state.py"], 30),
    ]
    try:
        for name, cmd, timeout in commands:
            print(f"Testing {name}", flush=True)
            with (args.output / (name + ".log")).open("w") as f:
                completed = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
            result["checks"][name] = {"returncode": completed.returncode,
                                      "pass": completed.returncode == 0}
            if completed.returncode:
                raise RuntimeError(name + " failed; inspect captured evidence")
        result["network_ddr_pl_pass"] = True
        # BootROM/U-Boot/kernel UART logs and artifact provenance must also be audited.
        print("PASS ping/SSH/DDR/PL; milestone still requires boot log/provenance audit")
    finally:
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
