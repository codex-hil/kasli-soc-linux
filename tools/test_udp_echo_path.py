#!/usr/bin/env python3
"""Verify UDP RX -> buffered echo FIFO -> TX, including per-beat lengths."""
import random
import struct
from migen import Module, Memory, Signal
from migen.sim import run_simulation, passive
from litex.soc.interconnect import stream
from liteeth.common import eth_udp_user_description
from liteeth.core.udp import LiteEthUDPRX, LiteEthUDPTX


def exercise(size):
    dut=Module()
    dut.submodules.rx=rx=LiteEthUDPRX(0xc0a802ce)
    dut.submodules.tx=tx=LiteEthUDPTX(0xc0a802ce)
    dut.submodules.fifo=fifo=stream.SyncFIFO(eth_udp_user_description(8),2048,buffered=True)
    dut.comb += [rx.source.connect(fifo.sink),
        fifo.source.connect(tx.sink,omit={'src_port','dst_port'}),
        tx.sink.src_port.eq(fifo.source.dst_port),tx.sink.dst_port.eq(fifo.source.src_port)]
    data=random.Random(size).randbytes(size)
    packet=struct.pack('!HHHH',33000,1234,size+8,0)+data
    wire=packet+bytes(max(0,26-len(packet)))
    received=[];complete=[]
    @passive
    def monitor():
        cycle=0
        while True:
            yield tx.source.ready.eq(cycle%7 not in (0,1))
            if (yield rx.source.valid) and (yield rx.source.ready):
                assert (yield rx.source.length)==size,'RX length'
            if (yield fifo.source.valid):
                assert (yield fifo.source.length)==size,'FIFO length'
            if (yield tx.source.valid) and (yield tx.source.ready):
                assert (yield tx.source.length)==size+8,'TX IP payload length'
                received.append((yield tx.source.data))
                if (yield tx.source.last):complete.append(True)
            cycle+=1
            yield
    def control():
        yield rx.sink.ip_address.eq(0xc0a8026b)
        yield rx.sink.protocol.eq(17)
        yield rx.sink.length.eq(size+8)
        for _ in range(10):yield
        for index,byte in enumerate(wire):
            yield rx.sink.valid.eq(1)
            yield rx.sink.data.eq(byte)
            yield rx.sink.be.eq(1)
            yield rx.sink.last.eq(index==len(wire)-1)
            yield
            while not (yield rx.sink.ready):yield
        yield rx.sink.valid.eq(0)
        for _ in range(5000):
            if complete:
                expected=struct.pack('!HHHH',1234,33000,size+8,0)+data
                assert bytes(received)==expected,(size,len(received),bytes(received[:8]).hex())
                return
            yield
        raise AssertionError(('UDP timeout',size,len(received)))
    fragment=dut.get_fragment()
    for special in fragment.specials:
        if isinstance(special,Memory):
            for port in special.ports:
                if port.dat_r is None:port.dat_r=Signal(special.width)
    run_simulation(fragment,[control(),monitor()])

if __name__=='__main__':
    for size in (1,17,64,128,512,1024,1400):exercise(size)
    print('PASS: UDP RX/FIFO/TX sizes 1..1400, payload/header lengths and output stalls')
