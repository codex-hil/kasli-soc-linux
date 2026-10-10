#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Measure both FMC clocks using hardware reciprocal counters, never wall-time gates."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def measure(registers, banks, cycles, reference_hz):
    old = {}
    for bank in banks:
        if registers.read(bank+'_status') & 1:
            raise RuntimeError('Counter already busy: '+bank)
        old[bank] = registers.read(bank+'_sequence')
        registers.write(bank+'_gate', cycles)
    for bank in banks:
        registers.write(bank+'_start', 1)
    deadline = time.monotonic()+4
    while any(registers.read(bank+'_sequence') == old[bank] for bank in banks):
        if time.monotonic() > deadline:
            raise TimeoutError('Counter completion watchdog')
        time.sleep(.002)
    output = {}
    for bank in banks:
        status = registers.read(bank+'_status')
        ticks = registers.read(bank+'_reference_ticks')
        actual = registers.read(bank+'_measured_cycles')
        if status != 2 or ticks == 0 or actual != cycles:
            raise RuntimeError(f'{bank}: status={status}, ticks={ticks}, cycles={actual}')
        if registers.read(bank+'_sequence') != ((old[bank]+1) & 0xffffffff):
            raise RuntimeError('Unexpected sequence change: '+bank)
        hz = actual*reference_hz/ticks
        output[bank] = dict(reference_ticks=ticks, measured_cycles=actual,
            frequency_hz=hz, offset_ppm=(hz/100000000-1)*1e6,
            one_tick_resolution_ppm=1e6/ticks)
    return output


def reset_counters(registers, banks):
    for bank in banks:
        registers.write(bank+'_reset', 1)
    time.sleep(.01)
    for bank in banks:
        registers.write(bank+'_reset', 0)
    time.sleep(.01)


def local(args):
    from fmc_adc import Registers, ADC, I2C
    config = json.loads(args.csr_json.read_text())
    if config['constants'].get('reciprocal_abi') != 1:
        raise RuntimeError('Requires reciprocal ABI 1')
    reference_hz = config['constants']['reciprocal_reference_hz']
    banks = ['frequency', 'frequency2', 'frequency_reference']
    registers = Registers(args.csr_json, args.device)
    second = Registers(args.csr_json, args.device, card=2)
    result = dict(started_utc=datetime.now(timezone.utc).isoformat(),
        reference='PS FCLK0 (nominal 100 MHz; not an absolute calibrated reference)',
        reference_hz=reference_hz,
        clock_only=bool(config['constants'].get('reciprocal_clock_only', 0)),
        oscillator_tuning_enabled=False,
        phase_lock=False, hardware_validated=False, samples=[], gate_checks=[],
        si570_registers={})
    args.output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    try:
        for bank in banks:
            if registers.read(bank+'_signature') != 0x52464331:
                raise RuntimeError('Counter signature mismatch: '+bank)
        for card, r in enumerate((registers, second), 1):
            ADC(r).initialize()
            result['si570_registers'][str(card)] = I2C(r).read(0x55, 7, 6)
        time.sleep(.1)
        reset_counters(registers, banks)
        for cycles in (100000, 1000000, 10000000, 100000000):
            row = measure(registers, banks, cycles, reference_hz)
            if row['frequency_reference']['reference_ticks'] != cycles:
                raise RuntimeError('Reference self-test: exact 1:1 ratio failed')
            result['gate_checks'].append(row)
        for sample in range(args.samples):
            row = measure(registers, banks, args.cycles, reference_hz)
            if row['frequency_reference']['reference_ticks'] != args.cycles:
                raise RuntimeError('Reference self-test failed during run')
            for bank in ('frequency', 'frequency2'):
                if abs(row[bank]['offset_ppm']) > 1000:
                    raise RuntimeError('Clock beyond initial +/-1000 ppm qualification range')
            row['elapsed_seconds'] = time.monotonic()-start
            row['utc'] = datetime.now(timezone.utc).isoformat()
            row['intercard_ppm'] = (row['frequency']['frequency_hz']/row['frequency2']['frequency_hz']-1)*1e6
            result['samples'].append(row)
            (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
            print(f"{sample+1}/{args.samples}: LPC {row['frequency']['offset_ppm']:+.6f} ppm; "
                  f"HPC {row['frequency2']['offset_ppm']:+.6f} ppm; "
                  f"LPC/HPC {row['intercard_ppm']:+.6f} ppm", flush=True)
        if args.test_clock_loss:
            original = registers.read('adc_control')
            try:
                # Stop only FMC1; FMC2 must still complete. No oscillator register writes.
                registers.write('adc_control', (original | 1) & ~2)
                time.sleep(.02)
                for bank in ('frequency', 'frequency2'):
                    registers.write(bank+'_gate', 1000000)
                    registers.write(bank+'_start', 1)
                time.sleep(3.1)
                status1 = registers.read('frequency_status')
                status2 = registers.read('frequency2_status')
                result['clock_loss'] = dict(card1_status=status1, card2_status=status2)
                if status1 != 4 or status2 != 2:
                    raise RuntimeError('Hardware missing-clock isolation test failed')
            finally:
                registers.write('adc_control', original | 1)
                time.sleep(.01)
                registers.write('adc_control', original)
                time.sleep(.1)
                reset_counters(registers, banks)
            recovered = measure(registers, banks, 1000000, reference_hz)
            result['clock_loss']['recovery'] = recovered
        for card, r in enumerate((registers, second), 1):
            if I2C(r).read(0x55, 7, 6) != result['si570_registers'][str(card)]:
                raise RuntimeError('Si570 frequency registers unexpectedly changed')
        result['statistics'] = {}
        for bank in ('frequency', 'frequency2', 'intercard'):
            values = [row['intercard_ppm'] if bank == 'intercard' else row[bank]['offset_ppm']
                      for row in result['samples']]
            times = [row['elapsed_seconds'] for row in result['samples']]
            mean_x, mean_y = statistics.mean(times), statistics.mean(values)
            variance_x = sum((x-mean_x)**2 for x in times)
            slope = sum((x-mean_x)*(y-mean_y) for x, y in zip(times, values))/variance_x if variance_x else 0
            result['statistics'][bank] = dict(mean_ppm=mean_y,
                end_minus_start_ppm=values[-1]-values[0],
                linear_drift_ppm_per_minute=slope*60,
                min_ppm=min(values), max_ppm=max(values),
                stddev_ppm=statistics.pstdev(values))
        result['hardware_validated'] = True
        with (args.output/'samples.csv').open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['elapsed_seconds', 'utc', 'lpc_hz', 'hpc_hz', 'lpc_ppm', 'hpc_ppm', 'intercard_ppm'])
            for row in result['samples']:
                writer.writerow([row['elapsed_seconds'], row['utc'],
                    row['frequency']['frequency_hz'], row['frequency2']['frequency_hz'],
                    row['frequency']['offset_ppm'], row['frequency2']['offset_ppm'], row['intercard_ppm']])
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        registers.mem.close(); second.mem.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', help='Run on ZC706 over SSH; omission means local MMIO')
    p.add_argument('--csr-json', type=Path, default=ROOT/'build/zc706-frequency-small/gateware/csr.json')
    p.add_argument('--bit', type=Path, default=ROOT/'build/zc706-frequency-small/gateware/gateware/top.bit')
    p.add_argument('--device', default='/dev/uio0')
    p.add_argument('--output', type=Path, default=ROOT/'build/zc706-frequency-small/hardware')
    p.add_argument('--samples', type=int, default=60)
    p.add_argument('--cycles', type=int, default=100000000)
    p.add_argument('--test-clock-loss', action='store_true')
    a = p.parse_args()
    if not 16 <= a.cycles <= 200000000 or not 1 <= a.samples <= 3600:
        p.error('Require 16..200000000 cycles and 1..3600 samples')
    if not a.host:
        local(a); return
    import ipaddress
    host = str(ipaddress.ip_address(a.host))
    manifest = json.loads((a.bit.parent/'manifest.json').read_text())
    digest = hashlib.sha256(a.bit.read_bytes()).hexdigest()
    if not manifest.get('reciprocal') or manifest['adc_cards'] != 2 or manifest['bitstream_sha256'] != digest:
        p.error('Requires matching successful two-card reciprocal bitstream manifest')
    ssh = ['ssh', '-i', str(ROOT/'build/ssh/id_ed25519'), '-o',
        'UserKnownHostsFile='+str(ROOT/'build/ssh/known_hosts'), '-o', 'HostKeyAlias=192.168.2.15',
        '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5', 'root@'+host]
    remote = '/tmp/zc706-frequency'
    subprocess.run(ssh+['mkdir -p '+remote], check=True, timeout=15)
    for name, path in [('measure_fmc_clocks.py', Path(__file__)),
                       ('fmc_adc.py', ROOT/'tools/fmc_adc.py'), ('csr.json', a.csr_json)]:
        subprocess.run(ssh+['cat > '+remote+'/'+name], input=path.read_bytes(), check=True, timeout=15)
    a.output.mkdir(parents=True, exist_ok=True)
    command = f'cd {remote} && python3 -u measure_fmc_clocks.py --csr-json csr.json --output results --samples {a.samples} --cycles {a.cycles}'
    if a.test_clock_loss:
        command += ' --test-clock-loss'
    try:
        with (a.output/'runner.log').open('w') as log:
            subprocess.run(ssh+[command], stdout=log, stderr=subprocess.STDOUT,
                check=True, timeout=a.samples*2.1+90)
    finally:
        with (a.output/'result.json').open('wb') as out:
            subprocess.run(ssh+['cat '+remote+'/results/result.json'], stdout=out, timeout=15, check=True)
    with (a.output/'samples.csv').open('wb') as out:
        subprocess.run(ssh+['cat '+remote+'/results/samples.csv'], stdout=out, check=True, timeout=15)
    result = json.loads((a.output/'result.json').read_text())
    result['bitstream_sha256'] = digest
    result['csr_json_sha256'] = hashlib.sha256(a.csr_json.read_bytes()).hexdigest()
    (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['statistics'], indent=2))


if __name__ == '__main__':
    main()
