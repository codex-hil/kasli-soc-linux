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
p.add_argument('--dual',action='store_true',help='Use the dual-detector target and regulator')
p.add_argument('--control',choices=['fmc2','both'],default='both',help='Dual target: tune FMC2 alone or both cards')
p.add_argument('--output',type=Path)
a=p.parse_args()
host_started=datetime.now(timezone.utc).isoformat()
if not 25<=a.seconds<=600:p.error('Require 25..600 seconds')
work=ROOT/('build/zc706-wr-pll-dual' if a.dual else 'build/zc706-wr-pll')
if a.output is None:a.output=work/'hardware'
bit=work/'gateware/gateware/top.bit'
csr=work/'gateware/csr.json'
manifest=json.loads((bit.parent/'manifest.json').read_text())
digest=hashlib.sha256(bit.read_bytes()).hexdigest()
if not manifest.get('wr_pll') or manifest.get('bitstream_sha256')!=digest:
    p.error('Requires matching successful WR PLL build')
if a.dual and manifest.get('wr_pll_cards')!=2:
    p.error('Requires the dual WR PLL build')
lockpath=Path('/home/codex-hil/.cache/zc706-210251842914.lock')
lockpath.parent.mkdir(parents=True,exist_ok=True)
with lockpath.open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o',
        'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),'-o','HostKeyAlias=192.168.2.15',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','root@'+str(a.host)]
    names=['fmc_adc.py','measure_fmc_clocks.py','wr_pll_control.py','run_wr_pll.py']
    if a.dual:names.append('run_wr_pll_dual.py')
    uploaded_files={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [csr,*[ROOT/'tools'/n for n in names]]}
    native=work/'i2c.so'
    if not native.exists():p.error('Build the native I2C backend first (make wr-pll-software)')
    uploaded_files[str(native.relative_to(ROOT))]=hashlib.sha256(native.read_bytes()).hexdigest()
    uploaded_files['software/wr_pll/i2c.c']=hashlib.sha256((ROOT/'software/wr_pll/i2c.c').read_bytes()).hexdigest()
    remote='/tmp/zc706-wr-pll-dual' if a.dual else '/tmp/zc706-wr-pll'
    subprocess.run(ssh+['mkdir -p '+remote],check=True,timeout=15)
    for name in names:
        subprocess.run(ssh+['cat > '+remote+'/'+name],input=(ROOT/'tools'/name).read_bytes(),check=True,timeout=15)
    subprocess.run(ssh+['cat > '+remote+'/csr.json'],input=csr.read_bytes(),check=True,timeout=15)
    subprocess.run(ssh+['cat > '+remote+'/i2c.so'],input=native.read_bytes(),check=True,timeout=15)
    a.output.mkdir(parents=True,exist_ok=True)
    runner='run_wr_pll_dual.py' if a.dual else 'run_wr_pll.py'
    command=f'cd {remote} && python3 -u {runner} --csr-json csr.json --output result.json --seconds {a.seconds}'
    if a.dual:command+=' --control '+a.control
    if a.loss_test:command+=' --loss-test'
    try:
        with (a.output/'runner.log').open('w') as log:
            subprocess.run(ssh+[command],stdout=log,stderr=subprocess.STDOUT,check=True,
                timeout=a.seconds*((3 if a.dual and a.control=='both' else 2) if a.loss_test else 1)+90)
    finally:
        with (a.output/'result.json').open('wb') as f:
            subprocess.run(ssh+['cat '+remote+'/result.json'],stdout=f,check=True,timeout=15)
        result=json.loads((a.output/'result.json').read_text())
        result['bitstream_sha256']=digest
        result['host_started_utc']=host_started
        result['host_finished_utc']=datetime.now(timezone.utc).isoformat()
        result['files']=uploaded_files
        (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if a.dual:
        summary={'initial':{k:v.get('statistics') for k,v in result.get('initial',{}).get('cards',{}).items()},
            'recoveries':[{k:v.get('statistics') for k,v in loss.get('recovered',{}).get('cards',{}).items()}
                for loss in result.get('clock_loss_tests',[])]}
    else:
        summary={k:v.get('statistics') for k,v in result.items() if k in ('initial','recovered')}
    print(json.dumps(summary,indent=2))
