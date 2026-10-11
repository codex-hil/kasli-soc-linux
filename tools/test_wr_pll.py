#!/usr/bin/env python3
"""Run bounded physical WR PLL qualification, preserve evidence and board ownership."""
import argparse
import fcntl
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--host',required=True,type=ipaddress.ip_address)
p.add_argument('--seconds',type=float,default=60)
p.add_argument('--loss-test',action='store_true')
p.add_argument('--output',type=Path,default=ROOT/'build/zc706-wr-pll/hardware')
a=p.parse_args()
host_started=datetime.now(timezone.utc).isoformat()
if not 25<=a.seconds<=600:p.error('Require 25..600 seconds')
bit=ROOT/'build/zc706-wr-pll/gateware/gateware/top.bit'
csr=ROOT/'build/zc706-wr-pll/gateware/csr.json'
manifest=json.loads((bit.parent/'manifest.json').read_text())
digest=hashlib.sha256(bit.read_bytes()).hexdigest()
if not manifest.get('wr_pll') or manifest.get('bitstream_sha256')!=digest:
    p.error('Requires matching successful WR PLL build')
lockpath=Path('/home/codex-hil/.cache/zc706-210251842914.lock')
lockpath.parent.mkdir(parents=True,exist_ok=True)
with lockpath.open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o',
        'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),'-o','HostKeyAlias=192.168.2.15',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','root@'+str(a.host)]
    uploaded_files={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [csr,*[ROOT/'tools'/n for n in ('fmc_adc.py','measure_fmc_clocks.py','wr_pll_control.py','run_wr_pll.py')]]}
    native=ROOT/'build/zc706-wr-pll/i2c.so'
    if not native.exists():p.error('Build the native I2C backend first (make wr-pll-software)')
    uploaded_files[str(native.relative_to(ROOT))]=hashlib.sha256(native.read_bytes()).hexdigest()
    remote='/tmp/zc706-wr-pll'
    subprocess.run(ssh+['mkdir -p '+remote],check=True,timeout=15)
    for name in ('fmc_adc.py','measure_fmc_clocks.py','wr_pll_control.py','run_wr_pll.py'):
        subprocess.run(ssh+['cat > '+remote+'/'+name],input=(ROOT/'tools'/name).read_bytes(),check=True,timeout=15)
    subprocess.run(ssh+['cat > '+remote+'/csr.json'],input=csr.read_bytes(),check=True,timeout=15)
    subprocess.run(ssh+['cat > '+remote+'/i2c.so'],input=native.read_bytes(),check=True,timeout=15)
    a.output.mkdir(parents=True,exist_ok=True)
    command=f'cd {remote} && python3 -u run_wr_pll.py --csr-json csr.json --output result.json --seconds {a.seconds}'
    if a.loss_test:command+=' --loss-test'
    try:
        with (a.output/'runner.log').open('w') as log:
            subprocess.run(ssh+[command],stdout=log,stderr=subprocess.STDOUT,check=True,
                timeout=a.seconds*(2 if a.loss_test else 1)+90)
    finally:
        with (a.output/'result.json').open('wb') as f:
            subprocess.run(ssh+['cat '+remote+'/result.json'],stdout=f,check=True,timeout=15)
        result=json.loads((a.output/'result.json').read_text())
        result['bitstream_sha256']=digest
        result['host_started_utc']=host_started
        result['host_finished_utc']=datetime.now(timezone.utc).isoformat()
        result['files']=uploaded_files
        (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v.get('statistics') for k,v in result.items() if k in ('initial','recovered')},indent=2))
