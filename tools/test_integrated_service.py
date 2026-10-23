#!/usr/bin/env python3
"""Board-side bounded service check; invoke only inside the host board lease."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    runtime = Path('/run/zc706-service-test')
    runtime.mkdir(exist_ok=False)
    process = subprocess.Popen([sys.executable, '-u', 'integrated_service.py',
                               '--csr-json', 'csr.json', '--runtime-dir', str(runtime)])
    record = dict(result='FAIL', snapshots=[])
    try:
        deadline = time.monotonic()+150
        running = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Service exited before stop request')
            status = runtime/'pll.status.json'
            if status.exists():
                snapshot = json.loads(status.read_text())
                if snapshot['state'] != 'running':
                    raise RuntimeError('Service is not running')
                record['snapshots'].append(snapshot)
                if all(card['last']['locked'] for card in snapshot['cards'].values()):
                    if running is None:
                        running = time.monotonic()
                    if time.monotonic()-running >= 40:
                        break
                else:
                    running = None
            time.sleep(1)
        else:
            raise RuntimeError('Continuous dual lock was not observed for 40 seconds')
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        record['returncode'] = process.wait(timeout=20)
        if (runtime/'pll.json').exists():
            result = json.loads((runtime/'pll.json').read_text())
            record['original_settings_restored'] = result.get('original_settings_restored', False)
            record['service_stopped'] = result.get('service_stopped', False)
        if record['returncode'] == 0 and record.get('original_settings_restored') and record.get('service_stopped'):
            record['shutdown_result'] = 'PASS'
        (Path('service-test.json')).write_text(json.dumps(record, indent=2)+'\n')
    if record.get('shutdown_result') != 'PASS':
        raise RuntimeError('Service shutdown/restoration failed')
    record['result'] = 'PASS'
    Path('service-test.json').write_text(json.dumps(record, indent=2)+'\n')
    print('PASS: autonomous initialization, dual PLL lock, SIGTERM restoration')


if __name__ == '__main__':
    main()
