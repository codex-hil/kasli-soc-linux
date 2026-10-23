#!/usr/bin/env python3
"""Exercise real async FIFOs and DMA writers with independent ADC clocks."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gateware'))
from migen import Module, Signal, Memory, ClockDomain
from migen.sim import run_simulation, passive
from litedram.common import LiteDRAMNativePort
from adc_ddr_writer import ADCToDDR


def exercise(stall=False, length=256, invalid=False, misaligned=False, real=False, frame_bad=False, command_pipeline=False, delayed_data=False):
    top=Module()
    top.clock_domains.cd_sys=ClockDomain('sys')
    top.clock_domains.cd_adc=ClockDomain('adc')
    top.clock_domains.cd_adc2=ClockDomain('adc2')
    ports=[]; writers=[]; ram={}; queues=[[],[]]
    signals=[]
    for i in range(2):
        port=LiteDRAMNativePort(mode='write',address_width=24,data_width=512)
        sample,aligned,frame=Signal(64,reset=0x1111222233334444+i),Signal(reset=1),Signal(8,reset=0 if frame_bad else 15)
        writer=ADCToDDR(port,sample,aligned,frame,'adc' if i==0 else 'adc2',i+1,fifo_depth=4,command_pipeline=command_pipeline)
        top.submodules += writer
        ports.append(port);writers.append(writer);signals.append((sample,aligned,frame))
    @passive
    def memory():
        cycle=0
        held=[None, None]
        while True:
            for i,port in enumerate(ports):
                # Native command address must remain stable throughout a stall.
                if held[i] is not None:
                    assert (yield port.cmd.valid)
                    assert (yield port.cmd.addr)==held[i], 'Address changed under backpressure'
                held[i]=(yield port.cmd.addr) if (yield port.cmd.valid) and not (yield port.cmd.ready) else None
                (yield port.cmd.ready.eq(not stall and cycle%7!=0))
                (yield port.wdata.ready.eq(bool(queues[i]) and cycle%5!=0 and (not delayed_data or cycle%97>=70)))
                if (yield port.cmd.valid) and (yield port.cmd.ready):
                    queues[i].append((yield port.cmd.addr))
                if (yield port.wdata.valid) and (yield port.wdata.ready):
                    assert queues[i]
                    addr=queues[i].pop(0)
                    assert addr not in ram,'Duplicate address'
                    ram[addr]=(yield port.wdata.data)
            cycle+=1
            yield
    def control():
        for i,w in enumerate(writers):
            yield w.base.storage.eq(i*0x10000+(1 if misaligned else 0))
            yield w.length.storage.eq(length)
            yield w.synthetic.storage.eq(not real)
        for _ in range(10):yield
        for run in range(3 if not stall and not invalid else 1):
            if run==2:
                yield top.cd_adc.rst.eq(1);yield top.cd_adc2.rst.eq(1)
                for _ in range(8):yield
                yield top.cd_adc.rst.eq(0);yield top.cd_adc2.rst.eq(0)
                for _ in range(8):yield
            # Rearm at a different nonzero base: queued addresses must not leak
            # from the previous capture, including after an ADC-domain reset.
            base_offset=(run+1)*0x20000
            for i,w in enumerate(writers):
                yield w.base.storage.eq(base_offset+i*0x10000+(1 if misaligned else 0))
            yield
            for w in writers:yield w.start.re.eq(1)
            yield
            for w in writers:yield w.start.re.eq(0)
            yield
            yield
            # Full stall is released after both FIFOs overflow, so completion must drain.
            for t in range(5000):
                if stall and t==500:
                    for port in ports:yield port.cmd.ready.eq(1)
                status=[]
                for w in writers:status.append((yield w.status.status))
                if all(s&2 for s in status):
                    assert not any(queues), "done before final memory write drained"
                    break
                yield
            else:raise AssertionError('Capture timeout')
            for i,w in enumerate(writers):
                status=yield w.status.status
                assert bool(status&16)==invalid,(status,invalid)
                if invalid:continue
                if stall:
                    assert status&4
                    assert (yield w.dropped.status)>0
                    assert (yield w.dropped.status)+(yield w.written.status)==length
                else:
                    assert status==(10 if frame_bad else 2),status
                    assert (yield w.written.status)==length
                    assert (yield w.dropped.status)==0
                    assert (base_offset+i*0x10000)//64 in ram, (i, len(ram), sorted(ram)[:8], sorted(ram)[-8:])
                    for index in range(length):
                        word=ram[(base_offset+i*0x10000)//64+index//8]
                        value=(word>>(64*(index%8)))&((1<<64)-1)
                        assert value == (0x1111222233334444+i if real else index | ((index^(0xadc00001+i))<<32)),(i,index,hex(value))
            ram.clear()
            for _ in range(15):yield
    if stall:
        # Bound stalls rather than permanent backpressure: the producer must finish even with drops.
        @passive
        def blocked_memory():
            cycle=0
            while True:
                for i,port in enumerate(ports):
                    yield port.cmd.ready.eq(cycle>550)
                    yield port.wdata.ready.eq(bool(queues[i]) and cycle>550)
                    if (yield port.cmd.valid) and (yield port.cmd.ready):queues[i].append((yield port.cmd.addr))
                    if (yield port.wdata.valid) and (yield port.wdata.ready):
                        ram[queues[i].pop(0)]=(yield port.wdata.data)
                cycle+=1;yield
        model=blocked_memory()
    else:model=memory()
    fragment=top.get_fragment()
    # Pinned Migen's simulator assumes dat_r even on write-only BRAM ports.
    # Add an unused read signal only to the simulation fragment.
    for special in fragment.specials:
        if isinstance(special,Memory):
            for port in special.ports:
                if port.dat_r is None:port.dat_r=Signal(special.width)
    clocks={'sys':12,'adc':10,'adc2':14}
    for i,w in enumerate(writers):
        for cd in w.fifo._fragment.clock_domains:
            clocks[cd.name]=(10 if i==0 else 14) if cd.name.startswith('from') else 12
    run_simulation(fragment,[control(),model],clocks=clocks)


if __name__ == "__main__":
    exercise()
    exercise(length=8)
    exercise(length=16)
    exercise(stall=True,length=1024)
    exercise(invalid=True,length=0)
    exercise(invalid=True,length=7)
    exercise(invalid=True,length=(1<<27)-8)  # wide end exceeds the 1-GiB window
    exercise(invalid=True,misaligned=True)
    exercise(real=True)
    exercise(frame_bad=True)
    print('PASS: independent-clock capture, consecutive runs and ADC reset, command/data stalls, overflow, frame failure, real-data path and invalid configuration')
