#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""WR-derived PI and bounded Si570 RFREQ control; no divider/flash/OTP writes.

PI update adapted from CERN WRPC softpll/spll_common.c (2010-2014),
Tomasz Wlostowski and Grzegorz Daniluk, GPL-2.0-or-later.
Source: pinned wrpc-sw-wrs-v4 c3f553d267f3b8bad4f4ff6c321cf214ab09b97a.
Si570 freeze-M protocol follows WR wr_si57x_interface and Skyworks datasheet.
"""
import ctypes
from pathlib import Path
import math
import time
from fmc_adc import I2C


class WRPI:
    def __init__(self, bias, minimum, maximum, shift=19):
        self.bias, self.minimum, self.maximum, self.shift = bias, minimum, maximum, shift
        self.integrator = 0

    def update(self, error, kp, ki):
        i_new = self.integrator + ki*error
        y = ((i_new + error*kp + (1 << (self.shift-1))) >> self.shift) + self.bias
        # Same saturating anti-windup decision as WRPC pi_update().
        if y < self.minimum:
            y = self.minimum
            if i_new > self.integrator:
                self.integrator = i_new
        elif y > self.maximum:
            y = self.maximum
            if i_new < self.integrator:
                self.integrator = i_new
        else:
            self.integrator = i_new
        return y


class TimedI2C(I2C):
    """Explicit >=5 us line times, avoiding Linux sleep's scheduler latency."""
    def lines(self, scl, sda):
        self.r.write('adc_i2c_w', scl | ((not sda) << 1) | (sda << 2))
        if scl:
            deadline = time.monotonic()+.1
            while not self.r.read('adc_i2c_r') & 2:
                if time.monotonic()>deadline:
                    raise TimeoutError('Si570 I2C SCL held low')
        deadline = time.perf_counter_ns()+5000
        while time.perf_counter_ns()<deadline:
            pass


class NativeI2C:
    """C backend retains ACK, stretch timeout and minimum line times."""
    def __init__(self, registers):
        self.r = registers
        self.lib = ctypes.CDLL(str(Path(__file__).with_name('i2c.so')))
        self.lib.wr_i2c.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_int, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_uint]
        self.lib.wr_i2c.restype = ctypes.c_int
        self.timed = (hasattr(self.lib, 'wr_i2c_timed') and
            registers.map['constants'].get('config_clock_frequency') == 100000000)
        if self.timed:
            self.lib.wr_i2c_timed.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_uint8,
                ctypes.c_void_p, ctypes.c_uint]
            self.lib.wr_i2c_timed.restype = ctypes.c_int

    def transfer(self, read, register, values):
        data = (ctypes.c_uint8*len(values))(*values)
        address = ctypes.addressof(ctypes.c_uint32.from_buffer(self.r.mem))
        if self.timed:
            error = self.lib.wr_i2c_timed(address, self.r._offset('adc_i2c_w'),
                self.r._offset('adc_i2c_r'), self.r._offset('probe_counter'),
                read, register, data, len(values))
        else:
            error = self.lib.wr_i2c(address, self.r._offset('adc_i2c_w'),
                self.r._offset('adc_i2c_r'), read, register, data, len(values))
        if error:
            raise OSError(error, 'Si570 native I2C transaction failed')
        return list(data)

    def read(self, address, register, length):
        if address != 0x55:
            raise ValueError('Native Si570 backend only supports address 0x55')
        return self.transfer(1, register, [0]*length)


class Si570:
    def __init__(self, registers, maximum_ppm=50):
        self.i2c = NativeI2C(registers) if Path(__file__).with_name('i2c.so').exists() else TimedI2C(registers)
        self.maximum_ppm = maximum_ppm
        self.original = self.i2c.read(0x55, 7, 6)
        self.control = self.i2c.read(0x55, 135, 1)[0]
        self.freeze_dco = self.i2c.read(0x55, 137, 1)[0]
        if self.control & 0xe1 or self.freeze_dco & 0x10:
            raise RuntimeError('Si570 is busy/frozen; refusing to adopt an unknown configuration')
        self.base = self.decode(self.original)
        if self.base == 0:
            raise RuntimeError('Invalid Si570 RFREQ')
        self.ppm = 0
        self.changed = False

    @staticmethod
    def decode(regs):
        return ((regs[1] & 63) << 32) | int.from_bytes(bytes(regs[2:]), 'big')

    def write(self, register, values):
        if isinstance(self.i2c, NativeI2C):
            self.i2c.transfer(0, register, values)
            return
        try:
            self.i2c.start(); self.i2c.send(0x55 << 1); self.i2c.send(register)
            for value in values:
                self.i2c.send(value)
        finally:
            self.i2c.stop()

    def program(self, ppm):
        if not math.isfinite(ppm) or abs(ppm) > self.maximum_ppm:
            raise ValueError('RFREQ outside bounded +/-50 ppm range')
        rfreq = round(self.base*(1+ppm*1e-6))
        if not 0 < rfreq < (1 << 38):
            raise ValueError('RFREQ overflows 38-bit field')
        desired = self.original[:]
        desired[1] = (desired[1] & 0xc0) | (rfreq >> 32)
        desired[2:] = list((rfreq & 0xffffffff).to_bytes(4, 'big'))
        self.changed = True
        try:
            self.write(135, [self.control | 0x20])  # Freeze M; never Freeze DCO/NewFreq.
            self.write(7, desired)
        finally:
            self.write(135, [self.control])
        if self.i2c.read(0x55, 7, 6) != desired:
            raise RuntimeError('Si570 RFREQ/divider readback mismatch')
        if self.i2c.read(0x55, 135, 1)[0] != self.control:
            raise RuntimeError('Si570 did not unfreeze M')
        self.ppm = (rfreq/self.base-1)*1e6
        return self.ppm

    def restore(self):
        if self.changed:
            self.program(0)
        if self.i2c.read(0x55, 7, 6) != self.original:
            raise RuntimeError('Si570 original registers were not restored')
        self.changed = False


def signed(value):
    return value-(1 << 32) if value & (1 << 31) else value


def phase_snapshot(registers, bank='wr_phase'):
    registers.write(bank+'_snapshot', 1)
    output = {name: registers.read(bank+'_'+name) for name in
        ('status', 'phase', 'raw_phase', 'events', 'rejected', 'ref_age', 'adc_age')}
    output['phase'] = signed(output['phase'])
    output['raw_phase'] = signed(output['raw_phase'])
    output['phase_ns'] = output['phase']*10/63
    return output
