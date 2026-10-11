#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded independent WR-derived phase PLLs on the two ZC706 FMC clocks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import gc
import os
from pathlib import Path
import signal
import statistics
import time
from fmc_adc import Registers, ADC
from measure_fmc_clocks import measure, reset_counters
from wr_pll_control import Si570, WRPI, phase_snapshot
from run_wr_pll import stopped

BANKS=('frequency','frequency2','frequency_reference')
PHASE_BANKS=('wr_phase','wr_phase2')
CRITERIA=dict(peak_phase_ns=10, stddev_phase_ns=3, mean_phase_ns=1,
    locked_fraction=.95, evaluation_seconds=20)


def reset_phases(registers):
    for r, bank in zip(registers, PHASE_BANKS):r.write(bank+'_reset',1)
    time.sleep(.01)
    for r, bank in zip(registers, PHASE_BANKS):r.write(bank+'_reset',0)
    time.sleep(.01)


def acquire(registers, oscillators, active):
    rows=[]
    for _ in range(3):
        row=measure(registers[0],BANKS,100000000,registers[0].map['constants']['reciprocal_reference_hz'])
        rows.append(dict(tune_ppm=[s.ppm for s in oscillators], measurement=row))
        for index in active:
            s=oscillators[index]
            s.program(s.ppm-row[BANKS[index]]['offset_ppm'])
    reset_phases(registers)
    return rows


def summarize(records, duration, oscillator):
    tail=[row for row in records if row['elapsed_seconds']>=max(0,duration-20)]
    phases=[row['phase']['phase_ns'] for row in tail]
    stats=dict(mean_phase_ns=statistics.mean(phases),
        min_phase_ns=min(phases), max_phase_ns=max(phases),
        stddev_phase_ns=statistics.pstdev(phases),
        median_update_seconds=statistics.median(row['dt'] for row in tail),
        locked_fraction=sum(row['locked'] for row in tail)/len(tail),
        last_tune_ppm=oscillator.ppm)
    passed=(stats['locked_fraction']>CRITERIA['locked_fraction']
        and max(map(abs,phases))<=CRITERIA['peak_phase_ns']
        and stats['stddev_phase_ns']<CRITERIA['stddev_phase_ns']
        and abs(stats['mean_phase_ns'])<CRITERIA['mean_phase_ns'])
    return dict(statistics=stats, criteria=CRITERIA, passed=passed)


def loop(registers, oscillators, active, duration, label, output):
    # Long generation-2 scans of phase records caused physical control gaps.
    # Reference counting continues; cyclic collection runs between bounded loops.
    enabled=gc.isenabled()
    gc.collect();gc.disable()
    try:
        # ctypes releases the GIL inside stateless native I2C transactions.
        # Context shutdown joins all updates before restoration can run.
        if len(active)==2:
            with ThreadPoolExecutor(max_workers=2,thread_name_prefix='si570') as pool:
                return _loop(registers,oscillators,active,duration,label,output,pool)
        return _loop(registers,oscillators,active,duration,label,output,None)
    finally:
        if enabled:gc.enable()


def program_pending(oscillators, pending, pool):
    if pool is None:
        return {i:oscillators[i].program(row['correction']) for i,row in pending.items()}
    futures={i:pool.submit(oscillators[i].program,row['correction']) for i,row in pending.items()}
    actuals={};errors=[]
    # Wait for BOTH buses even if one fails; restoration must not overlap I2C.
    for i,future in futures.items():
        try:actuals[i]=future.result()
        except Exception as exc:errors.append(f'FMC{i+1}: {exc}')
    if errors:raise RuntimeError('Si570 updates failed: '+'; '.join(errors))
    return actuals


def _loop(registers, oscillators, active, duration, label, output, pool):
    """Each PI uses its own sample interval; reciprocal gates have one owner."""
    r=registers[0]
    controllers={i:WRPI(round(oscillators[i].ppm*1e6),-50000000,50000000) for i in active}
    scale=1<<19
    kp={i:round(.15*(10/63)*1e6*scale) for i in active}
    start=time.monotonic()
    output['start_monotonic']=start
    previous={i:start for i in active}
    lock_count={i:0 for i in active}
    last_rejected={i:None for i in active}
    output.update(cards={str(i+1):dict(records=[]) for i in active},
        frequency_windows=[], criteria=CRITERIA, passed=False)
    sequences={bank:r.read(bank+'_sequence') for bank in BANKS}
    for bank in BANKS:
        r.write(bank+'_gate',100000000);r.write(bank+'_start',1)
    iteration=0
    while time.monotonic()-start<duration:
        pending={}
        for i in active:
            now=time.monotonic();dt=now-previous[i];previous[i]=now
            snapshot=phase_snapshot(registers[i],PHASE_BANKS[i])
            if snapshot['status']!=3:
                raise RuntimeError(f'FMC{i+1}: WR tag stream/helper lost: '+json.dumps(snapshot))
            if last_rejected[i] is not None and snapshot['rejected']!=last_rejected[i]:
                raise RuntimeError(f'FMC{i+1}: phase pipeline rejected an event')
            last_rejected[i]=snapshot['rejected']
            if abs(snapshot['phase_ns'])>500:
                raise RuntimeError(f'FMC{i+1}: phase escaped bounded acquisition region')
            ki=round(.3*dt*(10/63)*1e6*scale)
            correction=controllers[i].update(snapshot['phase'],kp[i],ki)/1e6
            s=oscillators[i]
            correction=s.ppm+max(-1,min(1,correction-s.ppm))
            pending[i]=dict(correction=correction,elapsed_seconds=now-start,dt=dt,phase=snapshot)
        actuals=program_pending(oscillators,pending,pool)
        for i,row in pending.items():
            lock_count[i]=lock_count[i]+1 if abs(row['phase']['phase_ns'])<=10 else 0
            output['cards'][str(i+1)]['records'].append(dict(elapsed_seconds=row['elapsed_seconds'],
                dt=row['dt'], phase=row['phase'],tune_ppm=actuals[i],locked=lock_count[i]>=30))
        new={bank:r.read(bank+'_sequence') for bank in BANKS}
        if all(new[bank]!=sequences[bank] for bank in BANKS):
            row=dict(elapsed_seconds=time.monotonic()-start)
            for bank in BANKS:
                status=r.read(bank+'_status');ticks=r.read(bank+'_reference_ticks')
                cycles=r.read(bank+'_measured_cycles')
                if status!=2 or cycles!=100000000 or not ticks:
                    raise RuntimeError('Concurrent reciprocal check failed: '+bank)
                if new[bank]!=((sequences[bank]+1)&0xffffffff):
                    raise RuntimeError('Unexpected reciprocal sequence: '+bank)
                row[bank]=dict(reference_ticks=ticks,measured_cycles=cycles,
                    offset_ppm=(cycles*r.map['constants']['reciprocal_reference_hz']/ticks/100000000-1)*1e6)
            if row['frequency_reference']['reference_ticks']!=100000000:
                raise RuntimeError('Reference counter self-check failed')
            row['locked']={str(i+1):lock_count[i]>=30 for i in active}
            output['frequency_windows'].append(row)
            for bank in BANKS:r.write(bank+'_start',1)
            sequences=new
        iteration+=1
        if iteration%50==0:
            parts=[]
            for i in active:
                last=output['cards'][str(i+1)]['records'][-1]
                parts.append(f"FMC{i+1} phase={last['phase']['phase_ns']:+.3f}ns "
                    f"tune={last['tune_ppm']:+.6f}ppm locked={last['locked']}")
            print(f'{label} t={time.monotonic()-start:.2f}s '+ ' | '.join(parts),flush=True)
        time.sleep(.0005)
    for i in active:
        card=output['cards'][str(i+1)]
        card.update(summarize(card['records'],duration,oscillators[i]))
    output['passed']=all(card['passed'] for card in output['cards'].values())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csr-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--control',choices=['fmc2','both'],default='both')
    p.add_argument('--loss-test',action='store_true')
    p.add_argument('--realtime',action='store_true',help='Run bounded control with SCHED_FIFO priority 10 (requires privilege)')
    p.add_argument('--preinitialized',action='store_true',
        help='Keep trained ADC receivers and active DMA state; caller owns initialization')
    a=p.parse_args()
    if not 25<=a.seconds<=600:p.error('Require 25..600 seconds per run')
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stopped)
    registers=[];oscillators=[]
    active=[1] if a.control=='fmc2' else [0,1]
    result=dict(started_utc=datetime.now(timezone.utc).isoformat(),hardware_validated=False,
        controlled_cards=[i+1 for i in active],phase_lock_requested=True,
        flash_otp_written=False,frequency_reference='PS FCLK0 nominal 100 MHz',
        cyclic_gc='disabled only during bounded phase-control loops',
        proportional_gain_ppm_per_ns=.15,integral_gain_ppm_per_ns_second=.3)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    try:
        if a.realtime:
            os.sched_setscheduler(0,os.SCHED_FIFO,os.sched_param(10))
        result['scheduler']=dict(policy=os.sched_getscheduler(0),priority=os.sched_getparam(0).sched_priority)
        for card in (1,2):registers.append(Registers(a.csr_json,'/dev/uio0',card=card))
        if registers[0].map['constants'].get('wr_phase_cards')!=2:
            raise RuntimeError('Requires matched dual WR phase target')
        for i,r in enumerate(registers):
            if r.read(PHASE_BANKS[i]+'_signature')!=0x57525031:
                raise RuntimeError(f'FMC{i+1}: phase ABI signature mismatch')
            if not a.preinitialized: ADC(r).initialize()
            oscillators.append(Si570(r))
        result['original_si570']={str(i+1):s.original for i,s in enumerate(oscillators)}
        reset_counters(registers[0],BANKS)
        result['frequency_acquisition']=acquire(registers,oscillators,active)
        result['initial']={}
        loop(registers,oscillators,active,a.seconds,'initial',result['initial'])
        if not result['initial']['passed']:raise RuntimeError('Initial phase hold qualification failed')
        if a.loss_test:
            result['clock_loss_tests']=[]
            for lost_index in active:
                r=registers[lost_index];other=1-lost_index
                control=r.read('adc_control')
                loss=dict(card=lost_index+1,other_card=other+1)
                result['clock_loss_tests'].append(loss)
                before=phase_snapshot(registers[other],PHASE_BANKS[other])
                try:
                    r.write('adc_control',control & ~2);time.sleep(.02)
                    loss['lost']=phase_snapshot(r,PHASE_BANKS[lost_index])
                    loss['other_before']=before
                    loss['other_during']=phase_snapshot(registers[other],PHASE_BANKS[other])
                    if loss['lost']['status']!=1:
                        raise RuntimeError('Missing clock failed to invalidate only its phase stream')
                    if loss['other_during']['status']!=3:
                        raise RuntimeError('Other FMC phase detector lost validity during isolated clock loss')
                    if loss['other_during']['events']==before['events']:
                        raise RuntimeError('Other FMC phase detector stopped producing tags')
                    oscillators[lost_index].restore()
                finally:
                    r.write('adc_control',control);time.sleep(.1)
                reset_counters(registers[0],BANKS)
                loss['reacquisition']=acquire(registers,oscillators,active)
                loss['recovered']={}
                loop(registers,oscillators,active,a.seconds,f'after_fmc{lost_index+1}_loss',loss['recovered'])
                if not loss['recovered']['passed']:raise RuntimeError('Recovered phase hold qualification failed')
                loss['passed']=True
        for i,s in enumerate(oscillators):
            if i not in active and s.i2c.read(0x55,7,6)!=s.original:
                raise RuntimeError('Untuned control card oscillator changed')
        result['hardware_validated']=True
    except BaseException as exc:
        result['error']=str(exc)
        raise
    finally:
        restore_errors=[]
        for i,s in enumerate(oscillators):
            try:s.restore()
            except BaseException as exc:restore_errors.append(f'FMC{i+1}: {exc}')
        for i,r in enumerate(registers):
            try:r.write(PHASE_BANKS[i]+'_reset',1)
            except BaseException as exc:restore_errors.append(f'phase reset FMC{i+1}: {exc}')
        result['original_settings_restored']=len(oscillators)==2 and not restore_errors
        if restore_errors:
            result['restoration_errors']=restore_errors;result['hardware_validated']=False
        result['finished_utc']=datetime.now(timezone.utc).isoformat()
        a.output.write_text(json.dumps(result,indent=2)+'\n')
        for r in registers:r.mem.close()
        if restore_errors:raise RuntimeError('PLL restoration failed: '+json.dumps(restore_errors))


if __name__=='__main__':main()
