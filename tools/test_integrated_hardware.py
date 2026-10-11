#!/usr/bin/env python3
"""Locked ZC706 bring-up: train DDR/ADC, then capture while both PLLs run."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import statistics
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--program',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    work=ROOT/'build/zc706-integrated';bit=work/'gateware/gateware/top.bit'
    digest=hashlib.sha256(bit.read_bytes()).hexdigest()
    manifest=json.loads((bit.parent/'manifest.json').read_text())
    if manifest['design']!='integrated' or manifest['bitstream_sha256']!=digest:
        raise RuntimeError('Matching integrated build required')
    record=dict(result='FAIL',bitstream_sha256=digest,files={})
    lock=open('/home/codex-hil/.cache/zc706-210251842914.lock','a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        if a.program:
            subprocess.run([ROOT/'.venv/bin/python',ROOT/'tools/boot_adc_jtag.py',
                '--host',a.host,'--bit',bit,'--output',a.output/'boot'],check=True)
            a.host=json.loads((a.output/'boot/result.json').read_text())['host']
        ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o',
            'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),'-o',
            'HostKeyAlias=192.168.2.15','-o','StrictHostKeyChecking=yes',
            '-o','ConnectTimeout=5','root@'+a.host]
        remote='/tmp/zc706-integrated'
        subprocess.run(ssh+['mkdir -p '+remote],check=True)
        sources=[(work/'pl-ddr-test','pl-ddr-test'),(work/'adc-ddr-read','adc-ddr-read'),
            (work/'gateware/csr.json','csr.json'),
            (work/'i2c.so','i2c.so')]
        for name in ('fmc_adc.py','sfp_probe.py','measure_fmc_clocks.py',
                     'wr_pll_control.py','run_wr_pll.py','run_wr_pll_dual.py','capture_adc_ddr.py'):
            sources.append((ROOT/'tools'/name,name))
        for source,name in sources:
            data=source.read_bytes();sha=hashlib.sha256(data).hexdigest()
            subprocess.run(ssh+[f'cat > {remote}/{name}; chmod 700 {remote}/{name}'],input=data,check=True)
            if subprocess.check_output(ssh+[f'sha256sum {remote}/{name}'],text=True).split()[0]!=sha:
                raise RuntimeError('Upload hash mismatch')
            record['files'][name]=sha
        def run(name,command,timeout=300):
            with (a.output/(name+'.log')).open('w') as log:
                subprocess.run(ssh+['cd '+remote+' && '+command],stdout=log,
                    stderr=subprocess.STDOUT,timeout=timeout,check=True)
        run('ddr','./pl-ddr-test')
        run('sfp','python3 sfp_probe.py --csr-json csr.json --init-clock --loopback 1000 --external --output sfp.json')
        run('train-adc', '''python3 -c 'from fmc_adc import Registers,ADC; rs=[Registers("csr.json","/dev/uio0",card=i) for i in (1,2)]; [(ADC(r).initialize(),ADC(r).calibrate()) for r in rs]; [r.mem.close() for r in rs]' ''')
        run('adc','python3 capture_adc_ddr.py --csr-json csr.json --reader ./adc-ddr-read --output initial --max-samples 4194304 --preinitialized')
        with (a.output/'pll.log').open('w') as log:
            pll=subprocess.Popen(ssh+['cd '+remote+' && python3 run_wr_pll_dual.py --csr-json csr.json --preinitialized --realtime --seconds 120 --output pll.json'],stdout=log,stderr=subprocess.STDOUT)
            try:
                import time
                time.sleep(15)
                run('concurrent-adc','python3 capture_adc_ddr.py --csr-json csr.json --reader ./adc-ddr-read --output concurrent --max-samples 4194304 --preinitialized')
                subprocess.run(['python3',str(ROOT/'tools/test_sfp_network.py'),'--repeat','50',
                    '--output',str(a.output/'network.json')],check=False,timeout=120)
                if pll.poll() is not None:raise RuntimeError('PLL ended before concurrent tests completed')
                if pll.wait(timeout=120):raise RuntimeError('Dual PLL qualification failed')
            finally:
                if pll.poll() is None:
                    # SIGTERM remote runner through its own bounded owner; no unrelated processes.
                    subprocess.run(ssh+["pkill -TERM -f '^python3 run_wr_pll_dual.py'"],check=False)
                    pll.wait(timeout=15)
        capture=json.loads(subprocess.check_output(ssh+['cat '+remote+'/concurrent/result.json'],text=True))
        phases=json.loads(subprocess.check_output(ssh+['cat '+remote+'/pll.json'],text=True))['initial']
        record['concurrent_phase']={}
        for card,values in phases['cards'].items():
            samples=[row['phase']['phase_ns'] for row in values['records']
                if capture['start_monotonic'] <= phases['start_monotonic']+row['elapsed_seconds'] <= capture['end_monotonic']]
            if len(samples)<100:raise RuntimeError('Insufficient concurrent phase records')
            stats=dict(samples=len(samples),peak_ns=max(map(abs,samples)),stddev_ns=statistics.pstdev(samples),mean_ns=statistics.mean(samples))
            record['concurrent_phase'][card]=stats
            if stats['peak_ns']>10 or stats['stddev_ns']>=3 or abs(stats['mean_ns'])>=1:
                raise RuntimeError('Concurrent phase qualification failed: '+card)
        network=json.loads((a.output/'network.json').read_text())
        record['network_result']=network['result']
        record['result']='PASS' if network['result']=='PASS' else 'PARTIAL'
        record['core_integration_passed']=True
    except Exception as exc:
        record['error']=str(exc)
        raise
    finally:
        if 'ssh' in locals():
            with (a.output/'board.tar').open('wb') as output:
                subprocess.run(ssh+['tar -C '+remote+' -cf - .'],stdout=output,check=False)
        (a.output/'validation.json').write_text(json.dumps(record,indent=2)+'\n')
        lock.close()

if __name__=='__main__':main()
