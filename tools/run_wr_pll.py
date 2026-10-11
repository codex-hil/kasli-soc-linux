#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded WR-style phase PLL for FMC1, with factory restoration on exit."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import statistics
import time
from fmc_adc import Registers, ADC, I2C
from measure_fmc_clocks import measure, reset_counters
from wr_pll_control import Si570, WRPI, phase_snapshot


def stopped(signum, frame):
    raise KeyboardInterrupt('PLL stop signal')


def reset_phase(r):
    r.write('wr_phase_reset', 1); time.sleep(.01)
    r.write('wr_phase_reset', 0); time.sleep(.01)


def acquire(r, oscillator):
    rows=[]
    for _ in range(3):
        result=measure(r,['frequency','frequency2','frequency_reference'],100000000,100000000)
        offset=result['frequency']['offset_ppm']
        rows.append(dict(tune_ppm=oscillator.ppm, measurement=result))
        oscillator.program(oscillator.ppm-offset)
    reset_phase(r)
    return rows


def loop(r, oscillator, duration, label):
    pi=WRPI(round(oscillator.ppm*1e6),-50000000,50000000)
    scale=1 << pi.shift
    kp=round(.1*(10/63)*1e6*scale)
    start=previous=time.monotonic()
    records=[]; windows=[]; lock_count=0
    last_rejected=None
    # Independent reciprocal verification runs concurrently with phase control.
    banks=['frequency','frequency2','frequency_reference']
    for bank in banks:
        r.write(bank+'_gate',100000000); r.write(bank+'_start',1)
    sequence=r.read('frequency_sequence')
    while time.monotonic()-start < duration:
        now=time.monotonic(); dt=now-previous; previous=now
        snapshot=phase_snapshot(r)
        if snapshot['status'] != 3:
            raise RuntimeError('WR helper/phase tag stream lost: '+json.dumps(snapshot))
        if last_rejected is not None and snapshot['rejected'] != last_rejected:
            raise RuntimeError('WR phase tag pipeline rejected an event')
        last_rejected=snapshot['rejected']
        if abs(snapshot['phase_ns']) > 500:
            raise RuntimeError('Phase escaped bounded acquisition region')
        # WR PI, with Ki adjusted for Linux's actual update interval.
        ki=round(.3*dt*(10/63)*1e6*scale)
        correction=pi.update(snapshot['phase'],kp,ki)/1e6
        if abs(correction-oscillator.ppm) > 1:
            correction=oscillator.ppm+max(-1,min(1,correction-oscillator.ppm))
        actual=oscillator.program(correction)
        lock_count=lock_count+1 if abs(snapshot['phase_ns']) <= 10 else 0
        records.append(dict(elapsed_seconds=now-start, dt=dt, label=label,
            phase=snapshot, tune_ppm=actual, locked=lock_count>=30))
        new_sequence=r.read('frequency_sequence')
        if new_sequence != sequence:
            row={}
            for bank in banks:
                status=r.read(bank+'_status'); ticks=r.read(bank+'_reference_ticks')
                cycles=r.read(bank+'_measured_cycles')
                if status!=2 or cycles!=100000000 or not ticks:
                    raise RuntimeError('Concurrent reciprocal verification failed: '+bank)
                row[bank]=dict(reference_ticks=ticks,measured_cycles=cycles,
                    offset_ppm=(cycles/ticks-1)*1e6)
            if row['frequency_reference']['reference_ticks'] != 100000000:
                raise RuntimeError('Reference self-check failed')
            row['elapsed_seconds']=now-start
            row['phase_locked']=lock_count>=30
            windows.append(row)
            for bank in banks:
                r.write(bank+'_start',1)
            sequence=new_sequence
        if len(records)%50==0:
            print(f"{label} t={now-start:.2f}s phase={snapshot['phase_ns']:+.3f}ns "
                  f"tune={actual:+.6f}ppm locked={lock_count>=30}",flush=True)
        time.sleep(.0005)
    tail=[row for row in records if row['elapsed_seconds']>=max(0,duration-20)]
    phases=[row['phase']['phase_ns'] for row in tail]
    stats=dict(mean_phase_ns=statistics.mean(phases),
        min_phase_ns=min(phases),max_phase_ns=max(phases),
        stddev_phase_ns=statistics.pstdev(phases),
        locked_fraction=sum(row['locked'] for row in tail)/len(tail),
        last_tune_ppm=oscillator.ppm)
    return dict(records=records,frequency_windows=windows,statistics=stats,
        criteria=dict(peak_phase_ns=10, stddev_phase_ns=3, mean_phase_ns=1,
            locked_fraction=.95, evaluation_seconds=20),
        passed=stats['locked_fraction']>.95 and max(map(abs,phases))<=10
            and stats['stddev_phase_ns']<3 and abs(stats['mean_phase_ns'])<1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csr-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--loss-test',action='store_true')
    a=p.parse_args()
    if not 25<=a.seconds<=600:
        p.error('Require 25..600 seconds per bounded run')
    signal.signal(signal.SIGTERM,stopped); signal.signal(signal.SIGINT,stopped)
    r=Registers(a.csr_json,'/dev/uio0'); second=Registers(a.csr_json,'/dev/uio0',card=2)
    oscillator=None
    result=dict(started_utc=datetime.now(timezone.utc).isoformat(), hardware_validated=False,
        card=1, second_card_tuned=False, phase_lock_requested=True, flash_otp_written=False)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    try:
        if r.map['constants'].get('wr_phase_abi') != 1 or r.read('wr_phase_signature')!=0x57525031:
            raise RuntimeError('Requires matched WR phase ABI 1 target')
        for reg in (r,second): ADC(reg).initialize()
        second_original=I2C(second).read(0x55,7,6)
        oscillator=Si570(r)
        result['original_si570']=oscillator.original
        reset_counters(r,['frequency','frequency2','frequency_reference'])
        result['frequency_acquisition']=acquire(r,oscillator)
        result['initial']=loop(r,oscillator,a.seconds,'initial')
        if not result['initial']['passed']:
            raise RuntimeError('Initial phase hold qualification failed')
        if a.loss_test:
            original=r.read('adc_control')
            try:
                r.write('adc_control',original & ~2); time.sleep(.02)
                lost=phase_snapshot(r)
                if lost['status'] & 2:
                    raise RuntimeError('Phase valid stayed asserted without FMC clock')
                result['clock_loss']=lost
                oscillator.restore()
            finally:
                r.write('adc_control',original); time.sleep(.1)
            reset_counters(r,['frequency','frequency2','frequency_reference'])
            result['reacquisition']=acquire(r,oscillator)
            result['recovered']=loop(r,oscillator,a.seconds,'recovered')
            if not result['recovered']['passed']:
                raise RuntimeError('Recovered phase hold qualification failed')
        if I2C(second).read(0x55,7,6)!=second_original:
            raise RuntimeError('Untuned FMC2 oscillator registers changed')
        result['hardware_validated']=True
    except BaseException as exc:
        result['error']=str(exc)
        raise
    finally:
        try:
            if oscillator:
                oscillator.restore(); result['factory_restored']=True
            r.write('wr_phase_reset',1)
        finally:
            result['finished_utc']=datetime.now(timezone.utc).isoformat()
            a.output.write_text(json.dumps(result,indent=2)+'\n')
            r.mem.close(); second.mem.close()


if __name__=='__main__':main()
