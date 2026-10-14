#!/usr/bin/env python3
"""Bounded, locked DDR lane comparison; always restore the golden PL image."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
LOCK=Path('/home/codex-hil/.cache/zc706-210251842914.lock')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',required=True)
    p.add_argument('--candidate-bist',action='store_true',help='Also run full reference DDR BIST on candidate before restoration')
    p.add_argument('--repeats',type=int,choices=range(1,4),default=1,
                   help='Repeat initialization/diagnostic without reloading PL (maximum 3).')
    p.add_argument('--diagnostic',choices=('lanes','controls','dqs-sweep','dq-dqs-sweep','dq-detail','dq-eye','dq-eye-no-retrain','dq-eye-reset'),default='lanes')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--candidate-bit',type=Path,default=ROOT/'build/zc706-integrated/gateware/gateware/top.bit')
    p.add_argument('--golden-bit',type=Path,default=ROOT/'build/zc706-adc-ddr/gateware/gateware/top.bit')
    p.add_argument('--software',type=Path,default=ROOT/'build/zc706-integrated/pl-ddr-test')
    p.add_argument('--golden-software',type=Path,default=ROOT/'build/zc706-adc-ddr/pl-ddr-test')
    a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    record={'diagnostic':a.diagnostic,'repeats':a.repeats,'hardware_access':True,'sd_qspi_written':False,'tests':{},'restoration_passed':False}
    for name,bit in [('candidate',a.candidate_bit),('golden',a.golden_bit)]:
        manifest=json.loads((bit.parent/'manifest.json').read_text())
        sha=hashlib.sha256(bit.read_bytes()).hexdigest()
        if not manifest.get('timing_passed') or sha!=manifest['bitstream_sha256']:
            raise ValueError('Matching timing-clean manifest required for '+name)
        if not manifest['physical_part'].startswith('xc7z045ffg900'):
            raise ValueError('Expected ZC706 part for '+name)
        record[name+'_bit_sha256']=sha
    host=a.host
    def boot(bit,name,sync_host=True):
        nonlocal host
        subprocess.run([ROOT/'.venv/bin/python',ROOT/'tools/boot_adc_jtag.py',
            *(['--host',host] if sync_host else []),'--bit',bit,'--output',a.output/name],check=True,timeout=150)
        host=json.loads((a.output/name/'result.json').read_text())['host']
    def test(binary,name,diagnostic):
        ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o',
             'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),'-o',
             'HostKeyAlias=192.168.2.15','-o','StrictHostKeyChecking=yes',
             '-o','ConnectTimeout=5','root@'+host]
        data=binary.read_bytes();sha=hashlib.sha256(data).hexdigest()
        path='/tmp/zc706-ddr-reference-test'
        subprocess.run(ssh+['cat > '+path+'; chmod 700 '+path],input=data,check=True,timeout=20)
        if subprocess.check_output(ssh+['sha256sum '+path],timeout=10).decode().split()[0]!=sha:
            raise RuntimeError('Diagnostic upload mismatch')
        with (a.output/(name+'.log')).open('w') as log:
            result=subprocess.run(ssh+[path+({'controls':' --diagnose-controls','lanes':' --diagnose-errors','dqs-sweep':' --sweep-dqs','dq-dqs-sweep':' --sweep-dq-dqs','dq-detail':' --dq-detail','dq-eye':' --dq-eye','dq-eye-no-retrain':' --dq-eye-no-retrain','dq-eye-reset':' --dq-eye-reset'}[a.diagnostic] if diagnostic else '')],
                stdout=log,stderr=subprocess.STDOUT,timeout=300)
        record['tests'][name]={'exit':result.returncode,'software_sha256':sha}
        return result.returncode
    def repeat_test(name):
        for run in range(a.repeats):
            suffix='' if a.repeats==1 else '-run'+str(run+1)
            test(a.software,name+'-'+a.diagnostic+suffix,True)
    with LOCK.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        candidate_boot_passed=False
        try:
            boot(a.candidate_bit,'candidate-boot')
            candidate_boot_passed=True
            repeat_test('candidate')
            if a.candidate_bist:test(a.golden_software,'candidate-bist',False)
        finally:
            try:
                boot(a.golden_bit,'restore-golden',sync_host=candidate_boot_passed)
                repeat_test('golden')
                record['restoration_passed']=test(a.golden_software,'golden-bist',False)==0
            finally:
                record['final_host']=host
                (a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        if not record['restoration_passed']:
            raise RuntimeError('Golden DDR restoration qualification failed')


if __name__=='__main__':main()
