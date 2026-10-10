#!/usr/bin/env python3
"""Program the isolated SFP target, qualify internal loopback, optionally test switch traffic."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", required=True, type=ipaddress.IPv4Address)
    p.add_argument("--program", action="store_true")
    p.add_argument("--external", action="store_true")
    p.add_argument("--frames", type=int, default=1000)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if not 1 <= a.frames <= 100000:
        p.error("--frames must be 1..100000")
    out = a.output or ROOT/"build/zc706-sfp/hardware"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    bit = ROOT/"build/zc706-sfp/gateware/gateware/top.bit"
    manifest = json.loads((bit.parent/"manifest.json").read_text())
    digest = hashlib.sha256(bit.read_bytes()).hexdigest()
    if manifest.get("design") != "sfp" or manifest.get("bitstream_sha256") != digest or not manifest.get("timing_passed"):
        raise RuntimeError("SFP bitstream must match its successful timing-checked build")
    result = {"result": "FAIL", "bitstream_sha256": digest,
        "program_requested": a.program, "external_requested": a.external,
        "hardware_validated": False, "input_sha256": {}}
    host = str(a.host)
    try:
        if a.program:
            command = [str(ROOT/".venv/bin/python"), str(ROOT/"tools/boot_adc_jtag.py"),
                "--host", host, "--sd", "--bit", str(bit), "--output", str(out/"boot")]
            with (out/"boot.log").open("w") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
            boot = json.loads((out/"boot/result.json").read_text())
            host = boot["host"]
            result["boot"] = boot
        ssh = ["ssh", "-i", str(ROOT/"build/ssh/id_ed25519"),
            "-o", "UserKnownHostsFile="+str(ROOT/"build/ssh/known_hosts"),
            "-o", "HostKeyAlias=192.168.2.15", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5", "root@"+host]
        result["management_host"] = host
        remote = "/tmp/sfp-"+digest[:16]
        subprocess.run(ssh+["mkdir -p "+remote], check=True, timeout=15)
        for source in [ROOT/"tools/sfp_probe.py", ROOT/"tools/fmc_adc.py",
                       ROOT/"build/zc706-sfp/gateware/csr.json"]:
            data = source.read_bytes()
            expected = hashlib.sha256(data).hexdigest()
            subprocess.run(ssh+["cat > "+remote+"/"+source.name], input=data, check=True, timeout=15)
            actual = subprocess.check_output(ssh+["sha256sum "+remote+"/"+source.name], timeout=15).decode().split()[0]
            if actual != expected:
                raise RuntimeError("Board input checksum mismatch")
            result["input_sha256"][source.name] = expected
        def probe(name, options):
            path = remote+"/"+name+".json"
            command = f"python3 {remote}/sfp_probe.py --csr-json {remote}/csr.json --output {path} "+options
            with (out/(name+".log")).open("w") as log:
                completed = subprocess.run(ssh+[command], stdout=log, stderr=subprocess.STDOUT, timeout=300)
            data = subprocess.check_output(ssh+["cat "+path], timeout=15)
            (out/(name+".json")).write_bytes(data)
            if completed.returncode:
                raise RuntimeError(f"Board {name} failed; see saved diagnostics")
            return json.loads(data)
        internal = probe("loopback", f"--init-clock --loopback {a.frames}")
        if internal.get("loopback", {}).get("result") != "PASS":
            raise RuntimeError("Physical loopback was not qualified")
        result["loopback"] = internal
        if a.external:
            external = probe("external", "--external")
            result["external"] = external
            if "module" not in external:
                result["network"] = {"result": "NOT_RUN", "reason": "SFP EEPROM did not respond"}
            elif external["status"]["sfp_status_status"] & 63 != 63:
                result["network"] = {"result": "NOT_RUN", "reason": "External GTX/PCS link is down"}
            else:
                subprocess.run([sys.executable, str(ROOT/"tools/test_sfp_network.py"),
                    "--output", str(out/"network.json")], check=True, timeout=300)
                result["network"] = json.loads((out/"network.json").read_text())
                result["external_after"] = probe("external-after", "")
                for name in ("mac_status_crc_errors", "mac_status_preamble_errors"):
                    if result["external_after"]["status"][name] != external["status"][name]:
                        raise RuntimeError("MAC error counter incremented during switch test")
        external_pass = result.get("network", {}).get("result") == "PASS"
        complete = not a.external or external_pass
        result.update(result="PASS" if complete else "PARTIAL", hardware_validated=True,
                      loopback_passed=True, external_passed=external_pass,
                      all_requested_tests_passed=complete)
    except Exception as e:
        result["error"] = str(e)
        raise
    finally:
        (out/"validation.json").write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
