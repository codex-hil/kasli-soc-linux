#!/usr/bin/env python3
"""Bounded live SD-runtime soak: independent ADCs, DDR, PLL status and SFP.

Leaves the existing PLL service running; no reset, clock reinitialization,
analog frontend changes, SD Wire selection or boot-media writes. PLL status is
sampled, not a continuous phase/jitter recording. Captures use digital patterns.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import ipaddress
import json
from pathlib import Path
import shlex
import statistics
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

STATE_HELPER='''import json,sys
from pathlib import Path
sys.path.insert(0,'/opt/zc706-integrated')
from fmc_adc import Registers,ADC
mode,path=sys.argv[1:]
saved=json.loads(Path(path).read_text()) if mode=='restore' else {}
for card in (1,2):
 r=Registers('/etc/litex/csr.json','/dev/uio0',card);a=ADC(r)
 try:
  if r.read('adc_dma_status')&1:raise RuntimeError('Active DMA: restoration needs PL recovery')
  fields=['adc_control','adc_dma_base','adc_dma_length','adc_dma_synthetic']
  if mode=='snapshot':
   saved[str(card)]={name:r.read(name) for name in fields}
   saved[str(card)]['reg3']=a.reg(3);saved[str(card)]['reg4']=a.reg(4)
  else:
   row=saved[str(card)]
   a.reg(4,row['reg4']);a.reg(3,row['reg3'])
   for name in fields:r.write(name,row[name])
   if any(r.read(name)!=row[name] for name in fields) or a.reg(3)!=row['reg3'] or a.reg(4)!=row['reg4']:
    raise RuntimeError('ADC state restoration readback mismatch')
 finally:r.mem.close()
if mode=='snapshot':Path(path).write_text(json.dumps(saved,indent=2)+'\\n')
print(json.dumps(saved))
'''


REMOTE_RUNNER = """import os,signal,subprocess,sys
child=None
def stopped(*args):raise KeyboardInterrupt('Owned capture interrupted')
for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,stopped)
try:
 child=subprocess.Popen([sys.executable,'/opt/zc706-integrated/capture_adc_ddr.py',*sys.argv[1:]],start_new_session=True)
 code=child.wait(timeout=210)
finally:
 if child is not None and child.poll() is None:
  os.killpg(child.pid,signal.SIGINT)
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
sys.exit(code)
"""


def validate_phase_progress(previous, current):
    """Reject stale status, counter resets and replacement service processes."""
    if current['state']!='running' or current['pid']!=previous['pid']:
        raise RuntimeError('PLL service stopped or restarted')
    if current['elapsed_seconds']<=previous['elapsed_seconds']:
        raise RuntimeError('PLL status did not advance')
    for card in ('1','2'):
        before=previous['cards'][card]['last']['phase']['events']
        after=current['cards'][card]['last']['phase']['events']
        delta=(after-before)&0xffffffff
        if not 0<delta<0x80000000:
            raise RuntimeError('Phase event counter stalled or reset: FMC'+card)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True,type=ipaddress.IPv4Address)
    parser.add_argument('--seconds',type=int,default=600)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 120<=args.seconds<=1800:parser.error('Require 120..1800 seconds')
    args.output.mkdir(parents=True,exist_ok=False)
    tag=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    remote='/tmp/zc706-soak-'+tag
    ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o','BatchMode=yes',
         '-o','ConnectTimeout=5','-o','StrictHostKeyChecking=yes',
         '-o','UserKnownHostsFile='+str(Path.home()/'.local/state/zc706-sdwire-known-hosts'),
         '-o','HostKeyAlias=zc706-sdwire-mode-fix-20261027','root@'+str(args.host)]
    result=dict(result='FAIL',host=str(args.host),seconds_requested=args.seconds,
        started_utc=datetime.now(timezone.utc).isoformat(),cold_power_cycle_tested=False,
        remote_run_directory=remote,
        pll_observation='sampled status only; no continuous jitter/phase claim',
        analog_frontend_changed=False,reset_performed=False,boot_media_written=False,
        snapshots=[],captures=[],networks=[],restoration_passed=False)
    leases=[];jobs=[];snapshot_saved=False

    def command(text,timeout=20):
        completed=subprocess.run(ssh+[text],capture_output=True,text=True,timeout=timeout)
        if completed.returncode:raise RuntimeError(completed.stderr+completed.stdout)
        return completed.stdout

    def state(mode):
        completed=subprocess.run(ssh+['python3 - '+mode+' '+shlex.quote(remote+'/adc-state.json')],
                                 input=STATE_HELPER,capture_output=True,text=True,timeout=30)
        if completed.returncode:raise RuntimeError(completed.stderr+completed.stdout)
        return json.loads(completed.stdout)

    def probe(name):
        text=command('cd /opt/zc706-integrated && python3 sfp_probe.py --csr-json /etc/litex/csr.json '
            '--output '+shlex.quote(remote+'/'+name+'.json')+' >'+shlex.quote(remote+'/'+name+'.log')+
            ' && cat '+shlex.quote(remote+'/'+name+'.json'),30)
        data=json.loads(text)
        (args.output/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
        return data

    def poll_jobs():
        for job in jobs:
            if job.get('done'):continue
            code=job['process'].poll()
            if code is None:
                if time.monotonic()-job['started']>240:raise RuntimeError('Child timeout: '+job['label'])
                continue
            job['log'].close();job['done']=True
            if job['kind']=='capture':
                data=json.loads(command('cat '+shlex.quote(job['remote']+'/result.json')))
                result['captures'].append(dict(label=job['label'],data=data,returncode=code))
                (args.output/(job['label']+'.json')).write_text(json.dumps(data,indent=2)+'\n')
            else:
                data=json.loads((args.output/(job['label']+'.json')).read_text())
                result['networks'].append(dict(label=job['label'],data=data,returncode=code))
            if code or data['result']!='PASS':raise RuntimeError('Qualification failed: '+job['label'])
            print(job['label']+' PASS',flush=True)

    try:
        for path in [Path.home()/'.cache/zc706-210251842914.lock',
                     Path.home()/'.local/state/hil-storage/hil-storage-DP04I33Y.lock']:
            lease=path.open('a');leases.append(lease);fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        route=json.loads(subprocess.check_output(['ip','-j','route','get','192.168.2.206'],text=True))
        interface=route[0]['dev'];link=dict(route=route,interface=interface)
        for name in ('speed','duplex','operstate','carrier','address'):
            try:link[name]=(Path('/sys/class/net')/interface/name).read_text().strip()
            except OSError:link[name]=None
        (args.output/'host-link.json').write_text(json.dumps(link,indent=2)+'\n')
        if command('hostname').strip()!='zc706-linux':raise RuntimeError('Wrong management host')
        (args.output/'baseline.log').write_text(command('uname -a; cat /proc/meminfo; cat /proc/mounts; '
            'sha256sum /etc/litex/csr.json /opt/zc706-integrated/capture_adc_ddr.py; dmesg'))
        current=json.loads(command('cat /run/zc706-integrated/pll.status.json'))
        if current['state']!='running' or not all(row['last']['locked'] for row in current['cards'].values()):
            raise RuntimeError('Baseline requires both PLLs already locked')
        result['service_pid']=current['pid']
        rejected={card:row['last']['phase']['rejected'] for card,row in current['cards'].items()}
        expected=hashlib.sha256((ROOT/'tools/capture_adc_ddr.py').read_bytes()).hexdigest()
        actual=command('sha256sum /opt/zc706-integrated/capture_adc_ddr.py').split()[0]
        if actual!=expected:raise RuntimeError('Installed capture tool does not match checkout')
        result['capture_tool_sha256']=actual
        runtime=json.loads(command('cat /opt/zc706-integrated/runtime-manifest.json'))
        reader_hash=command('sha256sum /opt/zc706-integrated/adc-ddr-read').split()[0]
        if reader_hash!=runtime['files']['adc-ddr-read']:raise RuntimeError('Reader checksum mismatch')
        result['reader_sha256']=reader_hash
        command('mkdir '+shlex.quote(remote))
        subprocess.run(ssh+['cat > '+shlex.quote(remote+'/owned_capture.py')],
            input=REMOTE_RUNNER,text=True,check=True,timeout=15)
        result['saved_adc_state']=state('snapshot');snapshot_saved=True
        before=probe('sfp-before')
        start=time.monotonic();next_batch=0;last_progress=0
        while time.monotonic()-start<args.seconds:
            elapsed=time.monotonic()-start
            status=json.loads(command('cat /run/zc706-integrated/pll.status.json'))
            validate_phase_progress(result['snapshots'][-1]['status'] if result['snapshots'] else current,status)
            result['snapshots'].append(dict(host_elapsed_seconds=elapsed,status=status))
            if status['state']!='running' or status['pid']!=result['service_pid']:
                raise RuntimeError('PLL service stopped or restarted')
            for card,row in status['cards'].items():
                last=row['last'];phase=last['phase']
                if not last['locked'] or phase['status']!=3 or abs(phase['phase_ns'])>10:
                    raise RuntimeError('Sampled phase/lock failure: FMC'+card)
                if phase['rejected']!=rejected[card]:raise RuntimeError('New phase pipeline rejection: FMC'+card)
            poll_jobs()
            if next_batch<4 and elapsed>=next_batch*args.seconds/4:
                if any(not job.get('done') for job in jobs):raise RuntimeError('Previous batch exceeded its slot')
                label='capture-'+str(next_batch+1);path=remote+'/'+label
                log=(args.output/(label+'.log')).open('w')
                process=subprocess.Popen(ssh+['cd /opt/zc706-integrated && python3 '+shlex.quote(remote+'/owned_capture.py')+' '
                    '--csr-json /etc/litex/csr.json --reader ./adc-ddr-read --max-samples 4194304 '
                    '--preinitialized --realtime-start --output '+shlex.quote(path)],stdout=log,stderr=subprocess.STDOUT)
                jobs.append(dict(kind='capture',label=label,remote=path,process=process,log=log,started=time.monotonic()))
                label='network-'+str(next_batch+1);log=(args.output/(label+'.log')).open('w')
                process=subprocess.Popen(['python3',str(ROOT/'tools/test_sfp_network.py'),'--repeat','1000',
                    '--output',str(args.output/(label+'.json'))],stdout=log,stderr=subprocess.STDOUT)
                jobs.append(dict(kind='network',label=label,process=process,log=log,started=time.monotonic()))
                next_batch+=1;print('Started batch '+str(next_batch),flush=True)
            if elapsed-last_progress>=60:
                print(f'Monitor {elapsed:.0f}/{args.seconds}s; PLL PID unchanged, both locked',flush=True)
                last_progress=elapsed
            time.sleep(2)
        result['observed_seconds']=time.monotonic()-start
        deadline=time.monotonic()+180
        while any(not job.get('done') for job in jobs):
            poll_jobs()
            if time.monotonic()>deadline:raise RuntimeError('Final jobs did not complete')
            time.sleep(1)
        after=probe('sfp-after')
        names=('mac_status_crc_errors','mac_status_preamble_errors','sfp_status_clock_faults')
        result['network_error_deltas']={name:(after['status'][name]-before['status'][name])&0xffffffff for name in names}
        if any(result['network_error_deltas'].values()):raise RuntimeError('New MAC/clock errors')
        if len(result['captures'])!=4 or len(result['networks'])!=4:raise RuntimeError('Missing test batches')
        packets=sum(network['data']['completed_packets'] for network in result['networks'])
        names=('mac_status_udp_rx_frames','mac_status_udp_fifo_frames','mac_status_udp_tx_frames')
        result['udp_frame_deltas']={name:(after['status'][name]-before['status'][name])&0xffffffff for name in names}
        if any(value!=packets for value in result['udp_frame_deltas'].values()):
            raise RuntimeError('PL UDP counters do not match client packet count')
        result['phase_sample_statistics']={card:dict(samples=len(result['snapshots']),
            peak_ns=max(abs(s['status']['cards'][card]['last']['phase']['phase_ns']) for s in result['snapshots']),
            mean_ns=statistics.mean(s['status']['cards'][card]['last']['phase']['phase_ns'] for s in result['snapshots']),
            stddev_ns=statistics.pstdev(s['status']['cards'][card]['last']['phase']['phase_ns'] for s in result['snapshots']))
            for card in ('1','2')}
        result['result']='PASS'
    except BaseException as exc:
        result['error']=str(exc)
    finally:
        # Let already-started finite hardware transactions finish. Never leave
        # an SSH child owning DMA after releasing the shared board lease.
        for job in jobs:
            if job['process'].poll() is None:
                try:job['process'].wait(timeout=330)
                except Exception as exc:result['cleanup_error']=str(exc)
            if not job['log'].closed:job['log'].close()
        if snapshot_saved:
            try:
                result['restored_adc_state']=state('restore')
                final=json.loads(command('cat /run/zc706-integrated/pll.status.json'))
                if final['state']!='running' or final['pid']!=result['service_pid'] or not all(row['last']['locked'] for row in final['cards'].values()):
                    raise RuntimeError('Baseline PLL service was not retained')
                result['restoration_passed']=True;result['final_status']=final
                (args.output/'final-kernel.log').write_text(command('dmesg'))
            except Exception as exc:result['restoration_error']=str(exc);result['result']='FAIL'
        result['finished_utc']=datetime.now(timezone.utc).isoformat()
        (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        for lease in reversed(leases):lease.close()
    print(json.dumps({key:value for key,value in result.items() if key not in ('snapshots','captures','networks','final_status')},indent=2))
    return 0 if result['result']=='PASS' and result['restoration_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
