#!/usr/bin/env python3
"""Validate actual 32-bit GP1 frontend lane/byte addressing across 1 GiB."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'upstream/litedram'))
from migen import Module, run_simulation
from litex.soc.interconnect import wishbone
from litedram.common import LiteDRAMNativePort
from litedram.frontend.wishbone import LiteDRAMWishbone2Native
from test.common import DRAMMemory


class SparseRAM(DRAMMemory):
    def __init__(self):
        super().__init__(512, 0)
        self.words = {}
    def _write(self, address, data, we):
        assert 0 <= address < (1 << 24)
        mask = sum(255 << (8*i) for i in range(64) if we & (1 << i))
        self.words[address] = (self.words.get(address, 0) & ~mask) | (data & mask)
    def _read(self, address):
        assert 0 <= address < (1 << 24)
        return self.words.get(address, 0)


class DUT(Module):
    def __init__(self):
        self.wb = wishbone.Interface(data_width=32, address_width=32)
        self.port = LiteDRAMNativePort('both', address_width=24, data_width=512)
        self.submodules.bridge = LiteDRAMWishbone2Native(self.wb, self.port,
            base_address=0x80000000)


dut = DUT()
ram = SparseRAM()
offsets = [0, 4, 60, 64, 0x1ffffffc, 0x20000000, 0x3ffffffc]


def control():
    for offset in offsets:
        yield from dut.wb.write((0x80000000+offset)//4, 0x53100000 ^ offset)
    for offset in offsets:
        value = yield from dut.wb.read((0x80000000+offset)//4)
        assert value == 0x53100000 ^ offset, (offset, value)
    # Byte enables must preserve the other bytes and neighboring 32-bit lanes.
    yield from dut.wb.write(0x80000004//4, 0xaabbccdd, sel=5)
    value = yield from dut.wb.read(0x80000004//4)
    assert value == ((0x53100004 & 0xff00ff00) | 0x00bb00dd), hex(value)
    value = yield from dut.wb.read(0x80000000//4)
    assert value == 0x53100000


run_simulation(dut, [control(), ram.write_handler(dut.port, 30),
    ram.read_handler(dut.port, 30)])
assert set(ram.words) == {offset//64 for offset in offsets}
print('PASS: 32-to-512-bit frontend, 1 GiB address boundaries, lane/byte enables, backpressure')
