#!/usr/bin/env python3
"""Validate SPI electrical transaction semantics against a small slave model."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fmc_adc', Path(__file__).resolve().parents[1]/'tools/fmc_adc.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Slave:
    def __init__(self):
        self.control = 10
        self.spi = 4
        self.bits = []
        self.words = []
        self.miso = 0
        self.selected = None

    def read(self, name):
        return self.control if name == 'adc_control' else self.miso

    def write(self, name, value):
        if name == 'adc_control':
            self.control = value
            return
        assert name == 'adc_spi_w'
        adc = bool(value & 16)
        dacs = (self.control >> 4) & 15
        assert not (adc and dacs), 'ADC and DAC selected together'
        assert dacs in (0, 1, 2, 4, 8), 'multiple DACs selected'
        selected = 'adc' if adc else (dacs.bit_length()-1 if dacs else None)
        if self.selected is not None and selected != self.selected:
            assert len(self.bits) == 16, 'chip-select ended an incomplete word'
            word = 0
            for bit in self.bits:
                word = (word << 1) | bit
            self.words.append((self.selected, word))
            self.bits = []
        if selected is not None and value & 1 and not self.spi & 1:
            assert value & 4, 'MOSI output disabled'
            self.bits.append((value >> 1) & 1)
            # A slave changes SDO before the software samples it on each edge.
            self.miso = (0x00a5 >> (16-len(self.bits))) & 1
        self.selected = selected
        self.spi = value

slave = Slave()
adc = module.ADC(slave)
with patch.object(module.time, 'sleep', lambda seconds: None):
    assert adc.spi(0x83c7) == 0xa5
    for channel in range(4):
        assert adc.spi(0x8000, dac=channel) == 0xa5
    # Final DAC CS release is a control write; observe it with one idle cycle.
    slave.write('adc_spi_w', 4)
assert slave.words == [('adc', 0x83c7)] + [(i, 0x8000) for i in range(4)]
assert slave.control == 10 and slave.spi == 4
print('PASS: 16-edge MSB-first SPI, slave readback, ADC/DAC chip-select exclusivity (model)')
