#!/usr/bin/env python3
"""Replay captured host ARP semantics through MAC CRC/CDC and ARP RTL."""
import struct
import zlib
from migen import Module, Memory, Signal, ClockDomain
from migen.sim import run_simulation, passive
from litex.soc.interconnect import stream
from liteeth.common import eth_phy_description
from liteeth.mac import LiteEthMAC
from liteeth.core.arp import LiteEthARP
from test_arp_reply import PL_IP, HOST_IP, PL_MAC, HOST_MAC


def exercise(rx_period=8, sys_period=12):
    dut=Module()
    for name in ('sys','eth_rx','eth_tx'):
        setattr(dut.clock_domains,'cd_'+name,ClockDomain(name))
    phy=Module();phy.dw=8
    phy.source=stream.Endpoint(eth_phy_description(8))
    phy.sink=stream.Endpoint(eth_phy_description(8))
    dut.submodules.mac=mac=LiteEthMAC(phy,dw=8,with_preamble_crc=True,
        with_sys_datapath=True,rx_cdc_depth=2048,tx_cdc_depth=2048,
        with_store_and_forward=True)
    dut.submodules.arp=arp=LiteEthARP(mac,PL_MAC,PL_IP,10000)
    dut.comb += phy.sink.ready.eq(1)
    replies=[];events=[];state={'send':False}
    @passive
    def monitor():
        while True:
            if (yield arp.rx.source.valid):events.append((yield arp.rx.source.reply))
            if (yield arp.table.response.valid):
                replies.append(((yield arp.table.response.failed),(yield arp.table.response.mac_address)))
            yield
    def control():
        yield arp.table.response.ready.eq(1)
        for _ in range(20):yield
        yield arp.table.request.valid.eq(1)
        yield arp.table.request.ip_address.eq(HOST_IP)
        for _ in range(100):
            if (yield arp.table.request.ready):break
            yield
        else:raise AssertionError('ARP request timeout')
        yield
        yield arp.table.request.valid.eq(0)
        for _ in range(100):yield
        state['send']=True
        for _ in range(1500):
            if replies:
                assert replies==[(0,HOST_MAC)],replies
                assert 1 in events
                assert (yield mac.core.rx_datapath.crc_errors.status)==0
                assert (yield mac.core.rx_datapath.preamble_errors.status)==0
                return
            yield
        raise AssertionError(('Full MAC ARP resolution timeout',events,replies))
    @passive
    def receive():
        while not state['send']:yield
        payload=struct.pack('!HHBBH6sI6sI',1,0x0800,6,4,2,
            HOST_MAC.to_bytes(6,'big'),HOST_IP,PL_MAC.to_bytes(6,'big'),PL_IP)
        ethernet=PL_MAC.to_bytes(6,'big')+HOST_MAC.to_bytes(6,'big')+b'\x08\x06'+payload
        ethernet+=bytes(60-len(ethernet))
        wire=b'\x55'*7+b'\xd5'+ethernet+struct.pack('<I',zlib.crc32(ethernet))
        for index,value in enumerate(wire):
            yield phy.source.valid.eq(1)
            yield phy.source.data.eq(value)
            yield phy.source.be.eq(1)
            yield phy.source.last.eq(index==len(wire)-1)
            yield
        yield phy.source.valid.eq(0)
        while True:yield
    fragment=dut.get_fragment()
    for special in fragment.specials:
        if isinstance(special,Memory):
            for port in special.ports:
                if port.dat_r is None:port.dat_r=Signal(special.width)
    run_simulation(fragment,{'sys':[control(),monitor()],'eth_rx':receive()},
        clocks={'sys':sys_period,'eth_rx':rx_period,'eth_tx':8})

if __name__=='__main__':
    exercise()
    exercise(rx_period=10,sys_period=14)
    print('PASS: padded host ARP reply through MAC CRC/store-forward/CDC/table, independent clocks')
