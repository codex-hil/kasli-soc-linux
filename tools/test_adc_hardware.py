#!/usr/bin/env python3
"""Program the J5 ADC snapshot target and retain physical acquisition evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--host', required=True, type=ipaddress.ip_address)
p.add_argument('--host-key-alias', default='192.168.2.15')
p.add_argument('--program', action='store_true')
p.add_argument('--card', type=int, choices=[1, 2], default=1)
p.add_argument('--jtag-serial', default='210251842914')
p.add_argument('--bit', type=Path, default=ROOT/'build/zc706-adc/gateware/gateware/top.bit')
p.add_argument('--csr-json', type=Path, default=ROOT/'build/zc706-adc/gateware/csr.json')
p.add_argument('--output', type=Path, default=ROOT/'build/zc706-adc/hardware')
args = p.parse_args()
if args.program:
    p.error('Live JTAG reconfiguration can stall GP0. Load ADC PL before Linux boot; omit --program.')
work = ROOT/'build/zc706-adc'
out = args.output
out.mkdir(parents=True, exist_ok=True)
bit = args.bit
manifest = json.loads((bit.parent/'manifest.json').read_text())
bit_hash = hashlib.sha256(bit.read_bytes()).hexdigest()
if manifest['design'] != 'fmc-adc' or manifest['bitstream_sha256'] != bit_hash:
    raise RuntimeError('Expected a matching successful ADC build manifest')
if args.card > manifest.get('adc_cards', 1):
    raise RuntimeError('Selected card is not present in this build')
ssh = ['ssh', '-i', str(ROOT/'build/ssh/id_ed25519'),
    '-o', 'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),
    '-o', 'HostKeyAlias='+args.host_key_alias, '-o', 'StrictHostKeyChecking=yes',
    '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=5',
    '-o', 'ServerAliveCountMax=3', 'root@'+str(args.host)]
remote = '/tmp/zc706-adc-bringup-card'+str(args.card)
result = {'started_utc': datetime.now(timezone.utc).isoformat(),
    'host': str(args.host), 'slot': 'J5 LPC' if args.card == 1 else 'J4 HPC', 'card': args.card, 'jtag_serial': args.jtag_serial,
    'program_requested': args.program, 'hardware_validated': False,
    'bitstream_sha256': bit_hash,
    'diagnostic_only': manifest.get('diagnostic_only', False),
    'diagnostic_sha256': hashlib.sha256((ROOT/'tools/fmc_adc.py').read_bytes()).hexdigest()}
ran = False
try:
    subprocess.run(ssh+['uname -a; python3 --version'], check=True, timeout=20)
    if args.program:
        loader = ROOT/'build/tools/oss-cad-suite/bin/openFPGALoader'
        with (out/'program.log').open('w') as log:
            subprocess.run([loader, '-b', 'zc706', '--usb-serial-num',
                args.jtag_serial, '--write-sram', bit], stdout=log,
                stderr=subprocess.STDOUT, check=True, timeout=60)
    subprocess.run(ssh+['mkdir -p '+remote], check=True, timeout=20)
    for name, source in [('fmc_adc.py', ROOT/'tools/fmc_adc.py'),
            ('csr.json', args.csr_json)]:
        subprocess.run(ssh+['cat > '+remote+'/'+name], input=source.read_bytes(),
            check=True, timeout=20)
    ran = True
    with (out/'adc-test.log').open('w') as log:
        subprocess.run(ssh+['cd '+remote+' && python3 -u fmc_adc.py --csr-json csr.json '
            '--device /dev/uio0 --card '+str(args.card)+' --output capture'], stdout=log,
            stderr=subprocess.STDOUT, check=True, timeout=240)
    for name in ('result.json', 'samples.bin', 'samples.csv'):
        with (out/name).open('wb') as output:
            subprocess.run(ssh+['cat '+remote+'/capture/'+name],
                stdout=output, check=True, timeout=20)
    capture = json.loads((out/'result.json').read_text())
    result['hardware_validated'] = capture.get('hardware_validated') is True and capture.get('result') == 'PASS'
    if not result['hardware_validated']:
        raise RuntimeError('Acquisition did not report PASS')
except Exception as exc:
    result['error'] = str(exc)
    if ran:
        with (out/'result.json').open('wb') as output:
            subprocess.run(ssh+['cat '+remote+'/capture/result.json'],
                stdout=output, timeout=20)
    raise
finally:
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (out/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
print((out/'result.json').read_text())
