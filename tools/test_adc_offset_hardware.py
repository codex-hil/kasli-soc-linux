#!/usr/bin/env python3
"""Run/retrieve physical offset sweeps over the existing ZC706 SSH connection."""
import argparse
from datetime import datetime,timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',required=True,type=ipaddress.ip_address)
    p.add_argument('--ranges',nargs='+',choices=['5V','0.5V','0.05V'],default=['5V','0.5V','0.05V'])
    p.add_argument('--output',type=Path,default=ROOT/'build/zc706-adc/hardware/offset')
    p.add_argument('--card',type=int,choices=[1,2],default=1)
    p.add_argument('--build-dir',type=Path,default=ROOT/'build/zc706-adc/gateware')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    build=a.build_dir
    manifest=json.loads((build/'gateware/manifest.json').read_text())
    digest=hashlib.sha256((build/'gateware/top.bit').read_bytes()).hexdigest()
    if manifest['design']!='fmc-adc' or manifest['bitstream_sha256']!=digest:
        p.error('Requires matching successful ADC bitstream manifest')
    if a.card > manifest.get('adc_cards',1):
        p.error('Selected card absent from the bitstream')
    ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o','UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),
         '-o','HostKeyAlias=192.168.2.15','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
         '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=3','root@'+str(a.host)]
    remote='/tmp/zc706-adc-offset-card'+str(a.card)
    result=dict(started_utc=datetime.now(timezone.utc).isoformat(),host=str(a.host),
                expected_bitstream_sha256=digest,slot='J5 LPC' if a.card==1 else 'J4 HPC',card=a.card,ranges={},
                diagnostic_sha256=hashlib.sha256((ROOT/'tools/test_adc_offset.py').read_bytes()).hexdigest(),
                driver_sha256=hashlib.sha256((ROOT/'tools/fmc_adc.py').read_bytes()).hexdigest())
    try:
        subprocess.run(ssh+['mkdir -p '+remote],check=True,timeout=20)
        for source,name in [(ROOT/'tools/fmc_adc.py','fmc_adc.py'),(ROOT/'tools/test_adc_offset.py','test_adc_offset.py'),(build/'csr.json','csr.json')]:
            subprocess.run(ssh+['cat > '+remote+'/'+name],input=source.read_bytes(),check=True,timeout=20)
        for span in a.ranges:
            out=a.output/span;out.mkdir(exist_ok=True)
            half={'5V':4096,'0.5V':512,'0.05V':64}[span]
            with (out/'test.log').open('w') as log:
                run=subprocess.run(ssh+[f'cd {remote} && python3 -u test_adc_offset.py --csr-json csr.json '
                    f'--card {a.card} --range {span} --half-span {half} --output offset-{span}'],stdout=log,stderr=subprocess.STDOUT,timeout=240)
            for name in ['result.json','summary.csv','samples.bin']:
                with (out/name).open('wb') as f:
                    subprocess.run(ssh+[f'cat {remote}/offset-{span}/{name}'],stdout=f,check=True,timeout=20)
            measurement=json.loads((out/'result.json').read_text())
            result['ranges'][span]=dict(result=measurement['result'],restored=measurement['restored'],
                sample_values_checked=measurement.get('sample_values_checked'),
                raw_sha256=hashlib.sha256((out/'samples.bin').read_bytes()).hexdigest())
            print(json.dumps(dict(range=span,**result['ranges'][span])),flush=True)
            if run.returncode or measurement['result']!='PASS' or not measurement['restored']:
                raise RuntimeError('Offset sweep failed: '+span)
        result['result']='PASS'
    except Exception as exc:
        result.update(result='FAIL',error=str(exc));raise
    finally:
        result['finished_utc']=datetime.now(timezone.utc).isoformat()
        (a.output/'validation.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
