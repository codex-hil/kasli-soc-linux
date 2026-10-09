#!/usr/bin/env python3
"""Load/train the matched combined target and validate both ADC DDR buffers."""
import argparse
from datetime import datetime,timezone
import hashlib,json,subprocess,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',required=True)
    p.add_argument('--program',action='store_true',help='Load via SD/U-Boot; keep default boot files and QSPI')
    p.add_argument('--analog',action='store_true')
    p.add_argument('--full-bist',action='store_true',help='Also run three full-capacity PL DDR BIST passes')
    p.add_argument('--max-samples',type=int,default=1<<22)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    work=ROOT/'build/zc706-adc-ddr'
    bit=work/'gateware/gateware/top.bit'
    manifest=json.loads((bit.parent/'manifest.json').read_text())
    digest=hashlib.sha256(bit.read_bytes()).hexdigest()
    if manifest.get('design')!='adc-ddr' or manifest.get('bitstream_sha256')!=digest:
        raise RuntimeError('Requires a successful matching combined build')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=a.output or work/'hardware'/stamp
    out.mkdir(parents=True,exist_ok=True)
    record=dict(result='FAIL',started_utc=stamp,bitstream_sha256=digest,
                host=a.host,analog_requested=a.analog,full_bist=a.full_bist,files={})
    try:
        host=a.host
        if a.program:
            print('Loading matched ADC DDR target through SD/U-Boot',flush=True)
            subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/boot_adc_jtag.py'),
                '--sd','--host',host,'--bit',str(bit),'--output',str(out/'boot')],check=True)
            host=json.loads((out/'boot/result.json').read_text())['host']
            record['host']=host
        ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o',
             'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),'-o',
             'HostKeyAlias=192.168.2.15','-o','StrictHostKeyChecking=yes',
             '-o','ConnectTimeout=5','root@'+host]
        sources=[(work/'pl-ddr-test','pl-ddr-test'),(work/'adc-ddr-read','adc-ddr-read'),
                 (work/'gateware/csr.json','adc-ddr-csr.json'),
                 (ROOT/'tools/fmc_adc.py','fmc_adc.py'),
                 (ROOT/'tools/capture_adc_ddr.py','capture_adc_ddr.py')]
        for source,name in sources:
            data=source.read_bytes();sha=hashlib.sha256(data).hexdigest()
            subprocess.run(ssh+[f'cat > /tmp/{name} && chmod 700 /tmp/{name}'],input=data,check=True)
            actual=subprocess.check_output(ssh+[f'sha256sum /tmp/{name}'],text=True).split()[0]
            if actual!=sha:raise RuntimeError('Upload hash mismatch: '+name)
            record['files'][name]=sha
        print('Initializing and training all eight SODIMM byte lanes',flush=True)
        with (out/'ddr-init.log').open('w') as log:
            subprocess.run(ssh+['/tmp/pl-ddr-test'+('' if a.full_bist else ' --init-only')],
                stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
        print('DDR training PASS; capturing independent ADC streams',flush=True)
        remote='/tmp/adc-ddr-'+stamp
        command=f'python3 /tmp/capture_adc_ddr.py --csr-json /tmp/adc-ddr-csr.json --output {remote} --max-samples {a.max_samples}'
        if a.analog:command+=' --analog'
        try:
            with (out/'capture.log').open('w') as log:
                subprocess.run(ssh+[command],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
        finally:
            # Retain diagnostics even after a board-side validation failure.
            with (out/'capture.tar').open('wb') as file:
                download=subprocess.run(ssh+[f'tar -C {remote} -cf - .'],stdout=file,stderr=subprocess.PIPE)
            if download.returncode==0:
                with tarfile.open(out/'capture.tar') as tar:tar.extractall(out/'capture',filter='data')
        captured=json.loads((out/'capture/result.json').read_text())
        if captured['result']!='PASS':raise RuntimeError('Capture verification did not pass')
        record['result']='PASS'
        record['capture_result']=str(out/'capture/result.json')
        print('PASS: dual independent-clock ADC DDR capture and complete readback',flush=True)
    except Exception as exc:
        record['error']=str(exc)
        raise
    finally:
        record['finished_utc']=datetime.now(timezone.utc).isoformat()
        (out/'validation.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':main()
