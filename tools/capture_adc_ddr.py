#!/usr/bin/env python3
"""Train both FMC receivers, capture to PL DDR, and verify every stored sample.

Run after matching pl-ddr-test --init-only has initialized this bitstream.
BNC inputs remain disconnected; real ADC checks use LTC2174 digital patterns.
The two ADC clocks and capture epochs are independent.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
from fmc_adc import ADC, Registers


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csr-json',required=True)
    p.add_argument('--reader',default='/tmp/adc-ddr-read')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-samples',type=int,default=1<<22)
    p.add_argument('--analog',action='store_true',help='Finally capture CH1 analog inputs at ±5 V, 50Ω OFF')
    a=p.parse_args()
    if a.max_samples<8192 or a.max_samples>1<<24 or a.max_samples%8:
        p.error('Maximum samples must be 8192..16777216 and a multiple of eight')
    a.output.mkdir(parents=True,exist_ok=True)
    result=dict(result='FAIL',synchronized=False,adc_clocks='independent',cards={},runs=[])
    opened=[];active=[]
    try:
        for card in (1,2):
            r=Registers(a.csr_json,'/dev/uio0',card)
            opened.append((card,r,ADC(r)))
            if r.map['constants'].get('adc_ddr_abi')!=1 or r.read('adc_dma_signature')!=0x41444452:
                raise RuntimeError('Requires ADC DDR ABI 1')
            if r.read('adc_control')!=1 or r.read('adc_ssr')!=0 or r.read('adc_dma_status')&1:
                raise RuntimeError('Requires both receivers stopped and DMA idle')
        for card,r,adc in opened:
            active.append(r)
            adc.initialize()
            training=adc.calibrate()
            # Qualify real receiver words before enabling the RAM stream.
            for pattern in (0,0x3fff,0x1235,0x2dca):adc.check_pattern(pattern)
            adc.pattern(0x1235 if card==1 else 0x2dca)
            result['cards'][str(card)]=dict(training=training,sample_rate_hz=adc.sample_rate(),
                adc_a2=adc.reg(2),base_offset=0x02000000 if card==1 else 0x10000000)
        sizes=sorted(set([8192,min(1<<18,a.max_samples),a.max_samples]))
        cases=[('sequence',n) for n in sizes]+[('adc_pattern',min(1<<18,a.max_samples))]
        # Repeat the long sequence capture after the real ADC path to exercise rearming.
        cases.append(('sequence',a.max_samples))
        if a.analog:cases.append(('analog',min(1<<18,a.max_samples)))
        for index,(mode,count) in enumerate(cases):
            run=dict(index=index,mode=mode,samples_per_card=count,cards={})
            result['runs'].append(run)
            if mode=='analog':
                run.update(range_full_scale_v=5,analog_50ohm=False)
                for card,r,adc in opened:
                    adc.pattern();adc.set_input(0,5,False)
                time.sleep(.1)
            for card,r,adc in opened:
                r.write('adc_dma_base',result['cards'][str(card)]['base_offset'])
                r.write('adc_dma_length',count)
                r.write('adc_dma_synthetic',int(mode=='sequence'))
            time.sleep(.002)
            for card,r,adc in opened:r.write('adc_dma_start',1)
            run['initial_status']={str(card):r.read('adc_dma_status') for card,r,_ in opened}
            if count >= 1<<18 and not all(s&1 for s in run['initial_status'].values()):
                raise RuntimeError('Long captures must overlap on both cards')
            deadline=time.monotonic()+5
            while not all(r.read('adc_dma_status')&2 for _,r,_ in opened):
                if time.monotonic()>deadline:raise TimeoutError('ADC DDR capture did not finish')
                time.sleep(.001)
            for card,r,adc in opened:
                status=r.read('adc_dma_status');written=r.read('adc_dma_written')
                dropped=r.read('adc_dma_dropped');ticks=r.read('adc_dma_ticks')
                state=dict(status=status,written_samples=written,dropped_samples=dropped,
                    adc_ssr=r.read('adc_ssr'),adc_a3=adc.reg(3),
                    system_ticks=ticks,system_clock_hz=r.map['constants']['config_clock_frequency'])
                run['cards'][str(card)]=state
                if status!=2 or written!=count or dropped:
                    raise RuntimeError(f'Card {card} DMA failed: {state}')
                state['effective_write_bytes_per_second']=count*8*state['system_clock_hz']/ticks
                pattern='seq' if mode=='sequence' else 'raw' if mode=='analog' else ('0x1235' if card==1 else '0x2dca')
                command=[a.reader,str(card),str(result['cards'][str(card)]['base_offset']),str(count),pattern]
                if index==0:command.append(str(a.output/f'card{card}-sequence.bin'))
                if mode=='analog':command.append(str(a.output/f'card{card}-analog.bin'))
                validation=subprocess.run(command,text=True,capture_output=True,timeout=300)
                state['reader_returncode']=validation.returncode
                state['reader_stdout']=validation.stdout;state['reader_stderr']=validation.stderr
                if validation.returncode:raise RuntimeError(f'Card {card} stored-data verification failed')
            run['result']='PASS'
            print(json.dumps(run),flush=True)
        result['result']='PASS'
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        for r in active:
            # A timeout leaves an active writer owned by this process. Resetting
            # only the ADC could corrupt an outstanding FIFO: leave RX running
            # in that exceptional case and require a whole-PL reset/reload.
            if r.read('adc_dma_status')&1:
                result['requires_pl_reload']=True
            else:
                r.write('adc_ssr',0);r.write('adc_control',1)
        for _,r,_ in opened:r.mem.close()
        (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: both independent-clock ADC streams stored and verified in PL DDR')


if __name__=='__main__':main()
