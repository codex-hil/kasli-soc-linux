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
import shlex
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',required=True)
    p.add_argument('--work-dir',type=Path,default=ROOT/'build/zc706-integrated')
    p.add_argument('--preflight-only',action='store_true',help='Validate artifacts without hardware access')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--program',action='store_true')
    p.add_argument('--external-network',action='store_true',help='Also test a physically connected external SFP link')
    p.add_argument('--sfp-diagnostic-only',action='store_true',help='Probe external SFP without internal-loopback prerequisite; always restore golden')
    p.add_argument('--srl-diagnostic-only',action='store_true',help='Test explicit SRL16E versus flip-flops; always restore golden')
    p.add_argument('--internal-loopback-only',action='store_true',help='Bounded internal PMA packet diagnostic with golden restoration')
    a=p.parse_args()
    if a.internal_loopback_only and (a.external_network or a.sfp_diagnostic_only or a.srl_diagnostic_only):
        p.error('Internal loopback diagnostic requires its own test scope')
    if a.internal_loopback_only and not a.program and not a.preflight_only:
        p.error('Internal loopback diagnostic requires --program for golden restoration')
    if a.srl_diagnostic_only and (a.sfp_diagnostic_only or a.external_network):
        p.error('SRL diagnostic requires its own test scope')
    if a.srl_diagnostic_only and not a.program and not a.preflight_only:
        p.error('SRL diagnostic requires --program for guaranteed golden restoration')
    a.output.mkdir(parents=True,exist_ok=True)
    work=a.work_dir.resolve();bit=work/'gateware/gateware/top.bit'
    digest=hashlib.sha256(bit.read_bytes()).hexdigest()
    manifest=json.loads((bit.parent/'manifest.json').read_text())
    allowed_designs=('srl','arp') if a.srl_diagnostic_only else ('integrated','sfp') if (a.sfp_diagnostic_only or a.internal_loopback_only) else ('integrated',)
    if manifest['design'] not in allowed_designs or not manifest.get('timing_passed') or manifest['bitstream_sha256']!=digest:
        raise RuntimeError('Matching timing-clean build required for the selected test scope')
    if manifest.get('experimental_srl_timing'):
        from build_pl import validate_srl_coverage
        validate_srl_coverage(bit.parent)
    if a.srl_diagnostic_only:
        from build_pl import hold_passed
        from check_srl_netlist import check
        timing=json.loads((bit.parent/'timing.json').read_text())
        if not timing['fmax'] or any(v['achieved'] < v['constraint'] for v in timing['fmax'].values()):
            raise RuntimeError('SRL setup timing must pass')
        if not hold_passed((bit.parent/'stage1.log').read_text()):
            raise RuntimeError('SRL hold validation required before hardware access')
        if manifest['design'] == 'arp':
            from check_arp_netlist import check as check_arp
            check_arp(bit.parent/'top.json', manifest.get('yosys_no_srl',False))
        else:
            check(bit.parent/'top.json')
    if a.sfp_diagnostic_only and manifest.get('sfp_refclk') == 'local':
        raise RuntimeError('Local-quad diagnostic cannot test the SFP connector')
    required=[work/'pl-ddr-test',work/'adc-ddr-read',work/'i2c.so',work/'gateware/csr.json']
    if a.sfp_diagnostic_only or a.srl_diagnostic_only or a.internal_loopback_only:
        required=[work/'gateware/csr.json']
    hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in required}
    if a.preflight_only:
        report=dict(hardware_access=False,qualification=False,bitstream_sha256=digest,artifacts=hashes)
        (a.output/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2));return
    golden=ROOT/'build/zc706-adc-ddr/gateware/gateware/top.bit'
    gm=json.loads((golden.parent/'manifest.json').read_text())
    if not gm.get('timing_passed') or hashlib.sha256(golden.read_bytes()).hexdigest()!=gm['bitstream_sha256']:
        raise RuntimeError('Matching timing-clean golden required for restoration')
    record=dict(result='FAIL',bitstream_sha256=digest,files={},restoration_passed=False)
    booted=False
    lock=open('/home/codex-hil/.cache/zc706-210251842914.lock','a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        if a.program:
            subprocess.run([ROOT/'.venv/bin/python',ROOT/'tools/boot_adc_jtag.py',
                '--host',a.host,'--bit',bit,'--output',a.output/'boot'],check=True)
            a.host=json.loads((a.output/'boot/result.json').read_text())['host']
            booted=True
        ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o',
            'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),'-o',
            'HostKeyAlias=192.168.2.15','-o','StrictHostKeyChecking=yes',
            '-o','ConnectTimeout=15','-o','ConnectionAttempts=3','root@'+a.host]
        remote='/tmp/zc706-integrated'
        subprocess.run(ssh+['mkdir -p '+remote],check=True)
        sources=[(work/'pl-ddr-test','pl-ddr-test'),(work/'adc-ddr-read','adc-ddr-read'),
            (work/'gateware/csr.json','csr.json'),
            (work/'i2c.so','i2c.so')]
        if a.sfp_diagnostic_only or a.srl_diagnostic_only or a.internal_loopback_only:
            sources=[(work/'gateware/csr.json','csr.json')]
        for name in ('fmc_adc.py','sfp_probe.py','measure_fmc_clocks.py',
                     'wr_pll_control.py','run_wr_pll.py','run_wr_pll_dual.py','capture_adc_ddr.py'):
            sources.append((ROOT/'tools'/name,name))
        if a.srl_diagnostic_only:
            sources = [(work/'gateware/csr.json','csr.json')] + [(ROOT/'tools'/n,n) for n in ('test_srl.py','test_arp_csr.py','sfp_probe.py','fmc_adc.py')]
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
        if a.srl_diagnostic_only:
            test_script = 'test_arp_csr.py' if manifest['design'] == 'arp' else 'test_srl.py'
            run('srl','python3 '+test_script+' --csr-json csr.json --output srl.json',timeout=30)
            record['srl']=json.loads(subprocess.check_output(ssh+['cat '+remote+'/srl.json'],text=True,timeout=15))
            record['result']=record['srl']['result']
            return
        if a.internal_loopback_only:
            run('sfp-internal','python3 sfp_probe.py --csr-json csr.json --init-clock --loopback 1000 --output sfp-internal.json',timeout=60)
            probe=json.loads(subprocess.check_output(ssh+['cat '+remote+'/sfp-internal.json'],text=True,timeout=15))
            record['internal_probe']=probe
            record['internal_loopback_result']=probe.get('loopback',{}).get('result','FAIL')
            record['result']=record['internal_loopback_result']
            if record['result'] != 'PASS':raise RuntimeError('Internal packet loopback failed')
            return
        if a.sfp_diagnostic_only:
            run('sfp-external','python3 sfp_probe.py --csr-json csr.json --init-clock --external --output sfp.json')
            probe=json.loads(subprocess.check_output(ssh+['cat '+remote+'/sfp.json'],text=True))
            record['external_probe']=probe
            if probe['status']['sfp_status_status'] & 63 == 63:
                # Preserve reset/link-up counters, then measure settled traffic
                # separately. Initial frame fragments can span a PCS reset.
                record['external_initial']=probe
                warmup=subprocess.run(['ping','-c','3','-i','.2','-W','1','192.168.2.206'],
                    capture_output=True,text=True,timeout=8)
                record['link_warmup']={'returncode':warmup.returncode,'stdout':warmup.stdout}
                run('sfp-ready','python3 sfp_probe.py --csr-json csr.json --output sfp-ready.json')
                probe=json.loads(subprocess.check_output(ssh+['cat '+remote+'/sfp-ready.json'],text=True))
                record['external_probe']=probe
                subprocess.run(['python3',str(ROOT/'tools/test_sfp_network.py'),
                    '--output',str(a.output/'network.json')],check=False,timeout=120)
                record['network_result']=json.loads((a.output/'network.json').read_text())['result']
            else:
                record['network_result']='NOT_RUN'
                record['network_reason']='External GTX/PCS link is down'
            run('sfp-after','python3 sfp_probe.py --csr-json csr.json --output sfp-after.json')
            after=json.loads(subprocess.check_output(ssh+['cat '+remote+'/sfp-after.json'],text=True))
            record['external_after']=after
            counters=('mac_status_tx_frames','mac_status_rx_frames',
                'mac_status_crc_errors','mac_status_preamble_errors','sfp_status_clock_faults')
            counters += tuple(n for n in probe['status'] if n.startswith('mac_status_arp_') and n != 'mac_status_arp_sender_ip' and not n.startswith('mac_status_arp_reply_header'))
            counters += tuple(n for n in probe['status'] if n.startswith('mac_status_udp_') and n.endswith('_frames'))
            record['network_counter_deltas']={n:(after['status'][n]-probe['status'][n]) & 0xffffffff for n in counters}
            record['result']='PASS' if record['network_result']=='PASS' else 'PARTIAL'
            if record['result']=='PASS' and any(record['network_counter_deltas'][n] for n in
                    ('mac_status_crc_errors','mac_status_preamble_errors','sfp_status_clock_faults')):
                record['result']='FAIL'
                record['error']='MAC or clock errors incremented during external traffic'
            return
        run('ddr','./pl-ddr-test')
        # External link qualification is independent of near-end PMA loopback.
        # Keep internal-only mode available, and report the omitted mode clearly.
        sfp_mode='--external ' if a.external_network else '--loopback 1000 '
        run('sfp','python3 sfp_probe.py --csr-json csr.json --init-clock '+sfp_mode+'--output sfp.json')
        record['internal_loopback_result']='NOT_RUN' if a.external_network else 'PASS'
        record['sfp_test_mode']='external' if a.external_network else 'internal-loopback'
        run('train-adc', '''python3 -c 'from fmc_adc import Registers,ADC; rs=[Registers("csr.json","/dev/uio0",card=i) for i in (1,2)]; [(ADC(r).initialize(),ADC(r).calibrate()) for r in rs]; [r.mem.close() for r in rs]' ''')
        run('adc','python3 capture_adc_ddr.py --csr-json csr.json --reader ./adc-ddr-read --output initial --max-samples 4194304 --preinitialized')
        pll_seconds=180 if a.external_network else 120
        with (a.output/'pll.log').open('w') as log:
            pll=subprocess.Popen(ssh+['cd '+remote+' && python3 run_wr_pll_dual.py --csr-json csr.json --preinitialized --realtime --seconds '+str(pll_seconds)+' --output pll.json'],stdout=log,stderr=subprocess.STDOUT)
            try:
                import time
                time.sleep(15)
                run('concurrent-adc','python3 capture_adc_ddr.py --csr-json csr.json --reader ./adc-ddr-read --output concurrent --max-samples 4194304 --preinitialized --realtime-start')
                if a.external_network:
                    run('sfp-before-network','python3 sfp_probe.py --csr-json csr.json --output sfp-before-network.json')
                    before=json.loads(subprocess.check_output(ssh+['cat '+remote+'/sfp-before-network.json'],text=True))
                    subprocess.run(['python3',str(ROOT/'tools/test_sfp_network.py'),'--repeat','50',
                        '--output',str(a.output/'network.json')],check=False,timeout=120)
                    run('sfp-after-network','python3 sfp_probe.py --csr-json csr.json --output sfp-after-network.json')
                    after=json.loads(subprocess.check_output(ssh+['cat '+remote+'/sfp-after-network.json'],text=True))
                    names=('mac_status_crc_errors','mac_status_preamble_errors','sfp_status_clock_faults')
                    record['network_error_deltas']={n:(after['status'][n]-before['status'][n]) & 0xffffffff for n in names}
                    if any(record['network_error_deltas'].values()):
                        raise RuntimeError('New MAC/clock errors during integrated external traffic')
                if pll.poll() is not None:raise RuntimeError('PLL ended before concurrent tests completed')
                if pll.wait(timeout=pll_seconds):raise RuntimeError('Dual PLL qualification failed')
            finally:
                if pll.poll() is None:
                    # SIGTERM remote runner through its own bounded owner; no unrelated processes.
                    stop_code = ("from pathlib import Path;import os,signal,sys;"
                        "pid=int(Path(sys.argv[1]).read_text());"
                        "cmd=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(bytes([0]));"
                        "assert b'run_wr_pll_dual.py' in cmd and b'pll.json' in cmd;"
                        "os.kill(pid,signal.SIGTERM)")
                    subprocess.run(ssh+['python3 -c '+shlex.quote(stop_code)+' '+
                        shlex.quote(remote+'/pll.pid')],check=True,timeout=15)
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
        network=json.loads((a.output/'network.json').read_text()) if a.external_network else {'result':'NOT_RUN'}
        record['network_result']=network['result']
        record['result']='PASS' if network['result']=='PASS' else 'PARTIAL'
        record['core_integration_passed']=True
    except Exception as exc:
        record['error']=str(exc)
        raise
    finally:
        try:
            if 'ssh' in locals():
                with (a.output/'board.tar').open('wb') as output:
                    subprocess.run(ssh+['tar -C '+remote+' -cf - .'],stdout=output,check=False,timeout=60)
        finally:
            try:
                if a.program:
                    subprocess.run([ROOT/'.venv/bin/python',ROOT/'tools/boot_adc_jtag.py',
                        *(['--host',a.host] if booted else []),'--bit',golden,
                        '--output',a.output/'restore-golden'],check=True,timeout=150)
                    a.host=json.loads((a.output/'restore-golden/result.json').read_text())['host']
                    restore_ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o',
                        'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),'-o',
                        'HostKeyAlias=192.168.2.15','-o','StrictHostKeyChecking=yes',
                        '-o','ConnectTimeout=15','-o','ConnectionAttempts=3','root@'+a.host]
                    data=(ROOT/'build/zc706-adc-ddr/pl-ddr-test').read_bytes()
                    subprocess.run(restore_ssh+['cat > /tmp/integrated-restore-bist; chmod 700 /tmp/integrated-restore-bist'],input=data,check=True,timeout=20)
                    with (a.output/'restored-golden-bist.log').open('w') as output:
                        subprocess.run(restore_ssh+['/tmp/integrated-restore-bist'],stdout=output,stderr=subprocess.STDOUT,check=True,timeout=300)
                    record['restoration_passed']=True
            finally:
                record['final_host']=a.host
                (a.output/'validation.json').write_text(json.dumps(record,indent=2)+'\n')
                lock.close()

if __name__=='__main__':main()
