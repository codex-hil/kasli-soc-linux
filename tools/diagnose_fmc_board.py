#!/usr/bin/env python3
"""Read ZC706 FMC presence and LPC FRU via the board mux; restore mux state."""
import argparse
import json
from pathlib import Path
from fmc_adc import Registers, I2C

class BoardRegisters:
    def __init__(self, registers):
        self.r = registers
    def read(self, name):
        return self.r.read(name.replace('adc_i2c_', 'board_i2c_'))
    def write(self, name, value):
        self.r.write(name.replace('adc_i2c_', 'board_i2c_'), value)

class BoardI2C(I2C):
    def raw_read(self, address):
        try:
            self.start(); self.send((address << 1) | 1)
            return self.receive(True)
        finally:
            self.stop()
    def raw_write(self, address, value):
        try:
            self.start(); self.send(address << 1); self.send(value)
        finally:
            self.stop()
    def present(self, address):
        try:
            self.start(); self.send(address << 1)
            return True
        except RuntimeError:
            return False
        finally:
            self.stop()

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--csr-json', required=True)
p.add_argument('--device', default='/dev/uio0')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
r = Registers(a.csr_json, a.device)
i = BoardI2C(BoardRegisters(r))
result = {'diagnostic': 'FMC presence/FRU', 'writes': 'temporary mux selection only; restored'}
saved = None
try:
    print('Reading board I2C mux', flush=True)
    saved = i.raw_read(0x74)
    result['mux_initial'] = saved
    # UG954 table 1-25: channel 3, U16 at 0x21. Read inputs only.
    i.raw_write(0x74, 1 << 3)
    inputs = i.read(0x21, 0, 2)
    result['expander_inputs'] = inputs
    # Rev. 1.2 sheet 37: P11 LPC PRSNT_M2C_B; P12 HPC PRSNT_M2C_B.
    result['lpc_present'] = not bool(inputs[1] & 2)
    result['hpc_present'] = not bool(inputs[1] & 4)
    print('FMC presence:', result['lpc_present'], result['hpc_present'], flush=True)
    i.raw_write(0x74, 1 << 6)
    result['lpc_eeprom_addresses'] = [hex(address) for address in range(0x50, 0x58) if i.present(address)]
    for address in result['lpc_eeprom_addresses']:
        # Standard FMC FRU EEPROM byte pointer; no data writes.
        data = i.read(int(address, 16), 0, 128)
        result['eeprom_'+address] = bytes(data).hex()
except Exception as exc:
    result['error'] = str(exc)
    raise
finally:
    try:
        if saved is not None:
            i.raw_write(0x74, saved)
    finally:
        r.mem.close()
        a.output.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2))
