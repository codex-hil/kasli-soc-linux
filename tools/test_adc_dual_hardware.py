#!/usr/bin/env python3
"""Qualify both independent FMC cards concurrently; never program live PL."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, type=ipaddress.ip_address)
    parser.add_argument('--host-key-alias', default='192.168.2.15')
    parser.add_argument('--bit', type=Path, default=ROOT/'build/zc706-adc-dual/gateware/gateware/top.bit')
    parser.add_argument('--csr-json', type=Path, default=ROOT/'build/zc706-adc-dual/gateware/csr.json')
    parser.add_argument('--output', type=Path, default=ROOT/'build/zc706-adc-dual/hardware')
    args = parser.parse_args()
    manifest = json.loads((args.bit.parent/'manifest.json').read_text())
    digest = hashlib.sha256(args.bit.read_bytes()).hexdigest()
    if manifest.get('adc_cards') != 2 or manifest.get('bitstream_sha256') != digest:
        parser.error('Requires the matching two-card bitstream manifest')
    args.output.mkdir(parents=True, exist_ok=True)
    result = dict(started_utc=datetime.now(timezone.utc).isoformat(),
                  hardware_validated=False, synchronized=False,
                  bitstream_sha256=digest, host=str(args.host), cards={})
    processes = []
    logs = []
    try:
        # Distinct remote directories and CSR banks; captures have independent epochs.
        for card in (1, 2):
            directory = args.output/f'card{card}'
            directory.mkdir(exist_ok=True)
            log = (directory/'runner.log').open('w')
            logs.append(log)
            command = [sys.executable, str(ROOT/'tools/test_adc_hardware.py'),
                       '--host', str(args.host), '--host-key-alias', args.host_key_alias,
                       '--card', str(card), '--bit', str(args.bit),
                       '--csr-json', str(args.csr_json), '--output', str(directory)]
            processes.append((card, subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)))
        for card, process in processes:
            result['cards'][str(card)] = {'exit_code': process.wait(timeout=300)}
            path = args.output/f'card{card}/validation.json'
            if path.exists():
                result['cards'][str(card)]['validation'] = json.loads(path.read_text())
        result['hardware_validated'] = all(
            item['exit_code'] == 0 and item.get('validation', {}).get('hardware_validated') is True
            for item in result['cards'].values()) and len(result['cards']) == 2
        if not result['hardware_validated']:
            raise RuntimeError('Both cards must pass; see card1/card2 runner and acquisition logs')
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        # Let the individual runners finish their bounded cleanup before closing logs.
        for _, process in processes:
            if process.poll() is None:
                process.wait(timeout=300)
        for log in logs:
            log.close()
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (args.output/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS: both cards, 278528 digital-pattern values and two independent 1024-sample snapshots')


if __name__ == '__main__':
    main()
