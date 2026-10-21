#!/usr/bin/env python3
"""Replay host ARP replies into upstream RX/table, without hardware."""
import struct
from migen import Module
from migen.sim import run_simulation, passive
from liteeth.core.arp import LiteEthARPRX, LiteEthARPTable
from decode_arp_snapshot import decode

PL_IP=0xc0a802ce
HOST_IP=0xc0a8026b
PL_MAC=0x02c0de706001
HOST_MAC=0x6c2b59f476e8

def exercise(padding, gap):
    dut=Module()
    dut.submodules.rx=rx=LiteEthARPRX(PL_MAC,PL_IP)
    dut.submodules.table=table=LiteEthARPTable(10000)
    dut.comb += rx.source.connect(table.sink)
    events=[]
    responses=[]
    @passive
    def monitor():
        while True:
            if (yield table.response.valid):
                responses.append(((yield table.response.failed),(yield table.response.mac_address)))
            if (yield rx.source.valid):
                events.append(((yield rx.source.reply),(yield rx.source.ip_address),(yield rx.source.mac_address)))
                raw=(yield rx.depacketizer.header)
                snapshot={f'mac_status_arp_reply_header{i}':(raw>>(32*i))&0xffffffff for i in range(7)}
                snapshot['mac_status_arp_sender_ip']=(yield rx.source.ip_address)
                decoded=decode(snapshot)
                assert decoded['sender_ip']=='192.168.2.107', decoded
                assert decoded['sender_mac']=='6c:2b:59:f4:76:e8', decoded
                assert decoded['target_ip']=='192.168.2.206', decoded
                assert decoded['opcode']==2 and decoded['sender_ip_matches_csr'], decoded
            yield
    def control():
        yield table.source.ready.eq(1)
        yield table.response.ready.eq(1)
        for _ in range(10):yield
        yield table.request.ip_address.eq(HOST_IP)
        yield table.request.valid.eq(1)
        for _ in range(100):
            if (yield table.request.ready):break
            yield
        else:raise AssertionError('Request not accepted')
        yield
        yield table.request.valid.eq(0)
        for _ in range(50):yield
        packet=struct.pack('!HHBBH6sI6sI',1,0x0800,6,4,2,HOST_MAC.to_bytes(6,'big'),HOST_IP,PL_MAC.to_bytes(6,'big'),PL_IP)+bytes(padding)
        for index,byte in enumerate(packet):
            yield rx.sink.data.eq(byte)
            yield rx.sink.valid.eq(1)
            yield rx.sink.last.eq(index==len(packet)-1)
            yield rx.sink.be.eq(1)
            yield
            while not (yield rx.sink.ready):yield
            yield rx.sink.valid.eq(0)
            for _ in range(gap):yield
        yield rx.sink.valid.eq(0)
        for _ in range(200):
            if responses:
                assert responses[-1] == (0,HOST_MAC), responses
                assert (1,HOST_IP,HOST_MAC) in events
                return
            yield
        if padding == 0:
            assert events == [], events
            return  # Document header-only behavior; not a valid padded wire frame.
        raise AssertionError(('ARP reply not resolved',padding,gap,events))
    run_simulation(dut,[control(),monitor()])

if __name__=='__main__':
    for padding in (0,18,32):
        for gap in (0,1,3):exercise(padding,gap)
    print('PASS: padded host replies resolve; header-only reply produces no RX event; byte gaps checked')
