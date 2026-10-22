#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual upstream ARP RX driven by a known padded byte stream, no GTX."""
import argparse
from pathlib import Path
import struct
from migen import Array, Constant, FSM, If, NextState, NextValue, Signal, ClockSignal
from litex.gen import LiteXModule
from litex.soc.interconnect.csr import CSRStorage, CSRStatus
from litex.soc.integration.export import get_csr_json
from liteeth.core.arp import LiteEthARPRX
from kasli_soc import BaseSoC
from zc706_sfp import SFPClock

PL_IP = 0xc0a802ce
HOST_IP = 0xc0a8026b
PL_MAC = 0x02c0de706001
HOST_MAC = 0x6c2b59f476e8


class ARPSelfTest(LiteXModule):
    def __init__(self):
        self.signature = CSRStatus(32, reset=0x41525031, name="signature")
        self.run = CSRStorage(1, name="run")
        self.gap = CSRStorage(2, name="gap")
        self.busy = CSRStatus(1, name="busy")
        self.sent = CSRStatus(32, name="sent")
        self.received = CSRStatus(32, name="received")
        self.errors = CSRStatus(32, name="errors")
        self.last_ip = CSRStatus(32, name="last_ip")
        self.last_mac_lo = CSRStatus(32, name="last_mac_lo")
        self.last_mac_hi = CSRStatus(16, name="last_mac_hi")
        self.rx = rx = LiteEthARPRX(PL_MAC, PL_IP)
        packet = struct.pack('!HHBBH6sI6sI', 1, 0x0800, 6, 4, 2,
            HOST_MAC.to_bytes(6,'big'), HOST_IP, PL_MAC.to_bytes(6,'big'), PL_IP) + bytes(18)
        rom = Array(Constant(byte, 8) for byte in packet)
        index = Signal(6)
        gap_count = Signal(2)
        wait_count = Signal(6)
        self.comb += [rx.sink.data.eq(rom[index]), rx.sink.last.eq(index == len(packet)-1),
            rx.sink.be.eq(1), rx.sink.error.eq(0), rx.sink.target_mac.eq(PL_MAC),
            rx.sink.sender_mac.eq(HOST_MAC), rx.sink.ethernet_type.eq(0x0806),
            rx.source.ready.eq(1)]
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE", If(self.run.storage,
            NextValue(index, 0), NextValue(self.busy.status, 1), NextState("SEND")))
        fsm.act("SEND", rx.sink.valid.eq(1), If(rx.sink.ready,
            If(rx.sink.last,
                NextValue(self.sent.status, self.sent.status + 1),
                NextValue(wait_count, 31), NextState("WAIT"))
            .Else(NextValue(index, index+1), NextValue(gap_count, self.gap.storage),
                If(self.gap.storage != 0, NextState("GAP")))))
        fsm.act("GAP", NextValue(gap_count, gap_count-1),
            If(gap_count == 1, NextState("SEND")))
        fsm.act("WAIT", NextValue(wait_count, wait_count-1),
            If(wait_count == 0, NextValue(self.busy.status, 0), NextState("IDLE")))
        self.sync += If(rx.source.valid & rx.source.ready,
            self.received.status.eq(self.received.status+1),
            self.last_ip.status.eq(rx.source.ip_address),
            self.last_mac_lo.status.eq(rx.source.mac_address[:32]),
            self.last_mac_hi.status.eq(rx.source.mac_address[32:]),
            If(~rx.source.reply | rx.source.request |
               (rx.source.ip_address != HOST_IP) | (rx.source.mac_address != HOST_MAC),
               self.errors.status.eq(self.errors.status+1)))


class ARPSoC(BaseSoC):
    def __init__(self):
        super().__init__("zc706", crg=SFPClock(), sys_clk_freq=50e6)
        self.cpu.cpu_params["i_M_AXI_GP0_ACLK"] = ClockSignal("sys")
        self.csr.add("probe", 1)
        self.arp = ARPSelfTest()
        self.csr.add("arp", 2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--board', choices=['zc706'], default='zc706')
    p.add_argument('--output-dir', required=True)
    a = p.parse_args()
    soc = ARPSoC()
    soc.finalize()
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out/'csr.json').write_text(get_csr_json(csr_regions=soc.csr_regions,
        constants=soc.constants, mem_regions=soc.mem_regions))
    soc.platform.build(soc, build_dir=str(out/'gateware'), run=False)


if __name__ == '__main__':
    main()
