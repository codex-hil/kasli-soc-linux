import fcntl,hashlib,json,re,subprocess,time
from pathlib import Path
import serial
ROOT=Path('/home/codex-hil/kasli-soc-linux').resolve()
out=ROOT/'build/zc706-arp-selftest-fixed/recovery';out.mkdir(exist_ok=True)
golden=ROOT/'build/zc706-adc-ddr/gateware/gateware/top.bit'
m=json.loads((golden.parent/'manifest.json').read_text());assert m['timing_passed'] and hashlib.sha256(golden.read_bytes()).hexdigest()==m['bitstream_sha256']
record={'result':'FAIL','restoration_passed':False}
with open('/home/codex-hil/.cache/zc706-210251842914.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  with serial.Serial('/dev/serial/by-id/usb-Silicon_Labs_CP2103_USB_to_UART_Bridge_Controller_0001-if00-port0',115200,timeout=.1) as uart:
   uart.write(b'\rsync && echo RECOVERY_SYNC_OK\r')
   data=b'';deadline=time.monotonic()+8
   while time.monotonic()<deadline:
    data+=uart.read(4096)
    if re.search(rb'\r?\nRECOVERY_SYNC_OK\r?\n',data):break
   (out/'sync-uart.log').write_bytes(data)
   if not re.search(rb'\r?\nRECOVERY_SYNC_OK\r?\n',data):raise RuntimeError('UART sync marker not confirmed')
   record['uart_sync_confirmed']=True
  subprocess.run([ROOT/'.venv/bin/python',ROOT/'tools/boot_adc_jtag.py','--bit',golden,'--output',out/'boot'],check=True,timeout=150)
  host=json.loads((out/'boot/result.json').read_text())['host'];record['final_host']=host
  ssh=['ssh','-i',str(ROOT/'build/ssh/id_ed25519'),'-o','UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'),'-o','HostKeyAlias=192.168.2.15','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','-o','ConnectionAttempts=3','root@'+host]
  subprocess.run(ssh+['cat > /tmp/recovery-bist; chmod 700 /tmp/recovery-bist'],input=(ROOT/'build/zc706-adc-ddr/pl-ddr-test').read_bytes(),check=True,timeout=60)
  with (out/'bist.log').open('w') as log:subprocess.run(ssh+['/tmp/recovery-bist'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
  record.update(result='PASS',restoration_passed=True)
 except Exception as e:
  record['error']=str(e);raise
 finally:(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
