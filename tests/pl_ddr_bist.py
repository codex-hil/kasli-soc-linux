#!/usr/bin/env python3
"""Check BIST top-of-capacity wrapping and error detection before hardware."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'upstream/litedram'))
from migen import Module, Signal, run_simulation
from migen.fhdl.specials import Memory
from litedram.common import LiteDRAMNativeWritePort, LiteDRAMNativeReadPort
from litedram.frontend.bist import (_LiteDRAMBISTGenerator, _LiteDRAMBISTChecker,
    LiteDRAMBISTGenerator, LiteDRAMBISTChecker)
from test.common import DRAMMemory


class DUT(Module):
    def __init__(self):
        self.wp = LiteDRAMNativeWritePort(address_width=4, data_width=32)
        self.rp = LiteDRAMNativeReadPort(address_width=4, data_width=32)
        self.submodules.writer = _LiteDRAMBISTGenerator(self.wp)
        self.submodules.reader = _LiteDRAMBISTChecker(self.rp)
        self.mem = DRAMMemory(32, 16, init=[0xdeadbeef]*16)


def check(random_data, corrupt):
    dut = DUT()
    def control():
        for block in (dut.writer, dut.reader):
            yield block.reset.eq(1)
        yield
        for block in (dut.writer, dut.reader):
            yield block.reset.eq(0)
            yield block.base.eq(32)
            yield block.end.eq(0)  # 64 bytes wraps in the 6-bit CSR.
            yield block.length.eq(32)
            yield block.random_data.eq(random_data)
        yield
        for block in (dut.writer, dut.reader):
            if block is dut.reader:
                assert dut.mem.mem[:8] == [0xdeadbeef]*8
                assert all(x != 0xdeadbeef for x in dut.mem.mem[8:])
                if corrupt:
                    dut.mem.mem[15] ^= 1
            yield block.start.eq(1)
            yield
            yield block.start.eq(0)
            for cycle in range(1000):
                if (yield block.done):
                    break
                yield
            else:
                raise AssertionError('BIST timeout')
            yield
        errors = yield dut.reader.errors
        assert errors == int(corrupt), (random_data, corrupt, errors)
    fragment = dut.get_fragment()
    # Current Migen's simulator expects a read signal even on write-only
    # FIFO memory ports. Add unused simulation signals; hardware is untouched.
    for memory in fragment.specials:
        if isinstance(memory, Memory):
            for port in memory.ports:
                if port.dat_r is None:
                    port.dat_r = Signal(memory.width)
    run_simulation(fragment, [control(), dut.mem.write_handler(dut.wp, 30),
        dut.mem.read_handler(dut.rp, 30)])


for random_data in (0, 1):
    for corrupt in (False, True):
        check(random_data, corrupt)
print('PASS: upper-half wrapped end, backpressure, sequential/PRBS data, injected error')

# Exercise the actual CSR control/status crossings used by the 50 MHz BIST.
class CDCDUT(Module):
    def __init__(self):
        self.wp = LiteDRAMNativeWritePort(address_width=4, data_width=32, clock_domain="gp1")
        self.rp = LiteDRAMNativeReadPort(address_width=4, data_width=32, clock_domain="gp1")
        self.submodules.writer = LiteDRAMBISTGenerator(self.wp)
        self.submodules.reader = LiteDRAMBISTChecker(self.rp)
        self.mem = DRAMMemory(32, 16, init=[0xdeadbeef]*16)


def check_cdc(corrupt):
    dut = CDCDUT()
    def pulse(csr):
        yield csr.wr_stb.eq(1)
        yield
        yield csr.wr_stb.eq(0)
        for _ in range(20):
            yield
    def control():
        for block in (dut.writer, dut.reader):
            yield from pulse(block.reset)
            yield block.base.storage.eq(32)
            yield block.end.storage.eq(0)
            yield block.length.storage.eq(32)
            yield block.random.storage.eq(1)
        yield
        for block in (dut.writer, dut.reader):
            if block is dut.reader and corrupt:
                dut.mem.mem[15] ^= 1
            yield from pulse(block.start)
            for _ in range(2000):
                if (yield block.done.status):
                    break
                yield
            else:
                raise AssertionError("BIST CSR CDC timeout")
        assert (yield dut.reader.errors.status) == int(corrupt)
        assert dut.mem.mem[:8] == [0xdeadbeef]*8
    fragment = dut.get_fragment()
    for memory in fragment.specials:
        if isinstance(memory, Memory):
            for port in memory.ports:
                if port.dat_r is None:
                    port.dat_r = Signal(memory.width)
    run_simulation(fragment, {"sys": [control()], "gp1": [
        dut.mem.write_handler(dut.wp, 30), dut.mem.read_handler(dut.rp, 30)]},
        clocks={"sys": 10, "gp1": 20})

for corrupt in (False, True):
    check_cdc(corrupt)
print("PASS: BIST CSR reset/start/configuration/status CDC at 100/50 MHz and injected error")
