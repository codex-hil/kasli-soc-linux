#!/usr/bin/env python3
"""Run destructive PL-only SODIMM diagnostics over the existing Linux SSH."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--host', default='192.168.2.15')
p.add_argument('--program', action='store_true', help='Load DDR bitstream into volatile PL SRAM first')
p.add_argument('--jtag-serial', default='210251842914')
args = p.parse_args()
work = ROOT/'build/zc706-ddr'
out = work/'hardware'
out.mkdir(exist_ok=True)
bit = work/'gateware/gateware/top.bit'
test = work/'pl-ddr-test'
ssh = ['ssh', '-i', str(ROOT/'build/ssh/id_ed25519'),
    '-o', 'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),
    '-o', 'ConnectTimeout=10', 'root@'+args.host]
result = {'started_utc': datetime.now(timezone.utc).isoformat(),
    'host': args.host, 'jtag_serial': args.jtag_serial,
    'program_requested': args.program, 'hardware_validated': False,
    'diagnostic_sha256': hashlib.sha256(test.read_bytes()).hexdigest(),
    'bitstream_sha256': hashlib.sha256(bit.read_bytes()).hexdigest()}
try:
    subprocess.run(ssh+['uname -a'], check=True)
    if args.program:
        loader = ROOT/'build/tools/oss-cad-suite/bin/openFPGALoader'
        with (out/'program.log').open('w') as log:
            # Explicit board and serial; SRAM only. No flash/SD operations.
            subprocess.run([loader, '-b', 'zc706', '--usb-serial-num',
                args.jtag_serial, '--write-sram', bit], stdout=log,
                stderr=subprocess.STDOUT, check=True, timeout=60)
    subprocess.run(ssh+['cat > /tmp/pl-ddr-test && chmod 700 /tmp/pl-ddr-test'],
        input=test.read_bytes(), check=True)
    with (out/'ddr-test.log').open('w') as log:
        subprocess.run(ssh+['/tmp/pl-ddr-test'], stdout=log,
            stderr=subprocess.STDOUT, check=True, timeout=240)
    result['hardware_validated'] = 'PASS: PL SODIMM init/leveling' in (out/'ddr-test.log').read_text()
    if not result['hardware_validated']:
        raise RuntimeError('Diagnostic exited without final PASS')
finally:
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (out/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
print((out/'ddr-test.log').read_text())
