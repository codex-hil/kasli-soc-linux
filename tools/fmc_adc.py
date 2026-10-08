#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bring-up/capture for the ZC706 J5 LiteX FMC ADC snapshot target (Linux root)."""
import argparse
import ctypes
import csv
import json
import mmap
import os
from pathlib import Path
import struct
import time


class Registers:
    def __init__(self, csr_json, device):
        self.map = json.loads(Path(csr_json).read_text())
        if self.map['constants'].get('adc_abi') != 1:
            raise RuntimeError('Requires FMC ADC ABI 1 CSR map')
        self.base = self.map['memories']['csr']['base']
        size = self.map['memories']['csr']['size']
        offset = self.base
        if Path(device).name.startswith('uio'):
            root = Path('/sys/class/uio') / Path(device).name / 'maps/map0'
            if int((root/'addr').read_text(), 0) != self.base or int((root/'size').read_text(), 0) < size:
                raise RuntimeError('UIO map does not cover this CSR region')
            offset = 0
        fd = os.open(device, os.O_RDWR | os.O_SYNC)
        try:
            self.mem = mmap.mmap(fd, size, flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=offset)
        finally:
            os.close(fd)
        if self.read('probe_signature') != 0x4b534f43:
            self.mem.close()
            raise RuntimeError('PL probe signature mismatch')

    def read(self, name):
        # MMIO needs one aligned word load/store. struct's little-endian
        # pack/unpack can use byte accesses on ARM, generating extra AXI
        # transactions and glitches on software-bitbanged SPI/I2C outputs.
        return ctypes.c_uint32.from_buffer(self.mem, self._offset(name)).value

    def write(self, name, value):
        if not 0 <= value <= 0xffffffff:
            raise ValueError('CSR value must fit an unsigned 32-bit word')
        ctypes.c_uint32.from_buffer(self.mem, self._offset(name)).value = value

    def _offset(self, name):
        offset = self.map['csr_registers'][name]['addr'] - self.base
        if offset < 0 or offset & 3 or offset + 4 > len(self.mem):
            raise ValueError('CSR must be an aligned 32-bit word inside the mapped region')
        return offset


class ADC:
    def __init__(self, registers):
        self.r = registers

    def spi(self, word, dac=None):
        # LTC2174: MSB first, change SDI on falling edge, sample SDO on rising.
        readback = 0
        self.r.write('adc_spi_w', 4)
        cs = 16 if dac is None else 0
        control = self.r.read('adc_control') & 15
        if dac is not None:
            self.r.write('adc_control', control | (1 << (4+dac)))
        self.r.write('adc_spi_w', 4 | cs)
        for bit in range(15, -1, -1):
            value = 4 | cs | (((word >> bit) & 1) << 1)
            self.r.write('adc_spi_w', value)
            time.sleep(0.00001)
            self.r.write('adc_spi_w', value | 1)
            readback = (readback << 1) | (self.r.read('adc_spi_r') & 1)
            time.sleep(0.00001)
            self.r.write('adc_spi_w', value)
        self.r.write('adc_spi_w', 4)
        if dac is not None:
            self.r.write('adc_control', control)
        return readback & 255

    def reg(self, address, value=None):
        if value is None:
            return self.spi(0x8000 | address << 8)
        self.spi(address << 8 | value)
        actual = self.reg(address)
        if actual != value:
            raise RuntimeError(f'ADC SPI register {address}: {actual:#x} != {value:#x}')

    def initialize(self):
        self.r.write('adc_control', 3)  # receiver reset, oscillator enabled
        self.spi(0x0080)  # Datasheet A0 RESET; self-clearing, write-only.
        time.sleep(0.005)
        self.reg(1, 0x20)  # two's complement; randomizer off; all channels awake
        self.reg(2, 0)     # two lanes, 16-bit serialization, 3.5 mA LVDS
        self.reg(3, 0)
        self.reg(4, 0)
        self.r.write('adc_control', 11)  # release DAC clear, keep RX reset
        for channel in range(4):
            self.spi(0x8000, dac=channel)  # nominal zero offset; EEPROM calibration later
        self.r.write('adc_control', 10)

    def set_taps(self, taps):
        if not all(0 <= x <= 31 for x in taps) or len(taps) != 9:
            raise ValueError('Nine IDELAY taps in range 0..31 required')
        self.r.write('adc_control', 11)
        for lane, tap in enumerate(taps):
            self.r.write(f'adc_tap{lane}', tap)
        time.sleep(0.001)
        self.r.write('adc_control', 10)

    def wait_aligned(self, timeout=0.25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.r.read('adc_status') & 3 == 3:
                return
            time.sleep(0.001)
        raise TimeoutError(f'ADC frame not aligned: status={self.r.read("adc_status"):#x}, '
                           f'frame={self.r.read("adc_frame"):#x}')

    def sample_rate(self):
        a = self.r.read('adc_count'); start = time.monotonic()
        time.sleep(0.05)
        b = self.r.read('adc_count'); end = time.monotonic()
        return ((b-a) & 0xffffffff)/(end-start)

    def pattern(self, value=None):
        if value is None:
            self.reg(3, 0)
        else:
            if not 0 <= value < 16384:
                raise ValueError('14-bit ADC pattern required')
            self.reg(4, value & 255)
            self.reg(3, 0x80 | value >> 8)
        time.sleep(0.001)

    def capture(self, external=False, timeout=2):
        self.wait_aligned()
        if self.r.read('adc_status') & 4:
            raise RuntimeError('Acquisition already busy')
        self.r.write('adc_control', 10 | (4 if external else 0))
        time.sleep(0.001)  # bundled trigger-mode configuration before request
        self.r.write('adc_arm', 1)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.r.read('adc_status')
            if status & 8 and not status & 4:
                break
            time.sleep(0.001)
        else:
            self.r.write('adc_control', 11)
            raise TimeoutError('Capture timed out (missing DCO, alignment, or trigger)')
        count, errors = self.r.read('adc_captured'), self.r.read('adc_errors')
        if count != 1024 or errors:
            raise RuntimeError(f'Invalid snapshot: count={count}, frame errors={errors}')
        words = []
        for address in range(count):
            self.r.write('adc_read_address', address)
            # A dummy read flushes the synchronous BRAM read before consuming data.
            self.r.read('adc_status')
            lo, hi = self.r.read('adc_data_low'), self.r.read('adc_data_high')
            words.append((lo & 65535, lo >> 16, hi & 65535, hi >> 16))
        return words

    def check_pattern(self, value):
        self.pattern(value)
        words = self.capture()
        expected = value << 2
        for index, row in enumerate(words):
            for channel, raw in enumerate(row):
                if raw != expected:
                    raise RuntimeError(f'Pattern {value:#06x}, sample {index}, channel {channel+1}: '
                                       f'{raw:#06x} != {expected:#06x}')

    def calibrate(self):
        good = []
        evidence = []
        for tap in range(32):
            self.set_taps([tap]*9)
            try:
                for value in (0x1235, 0x2dca):
                    self.check_pattern(value)
                good.append(tap)
                evidence.append({'tap': tap, 'pass': True})
            except (RuntimeError, TimeoutError) as exc:
                evidence.append({'tap': tap, 'pass': False, 'error': str(exc)})
        # Choose centre of the widest non-wrapping window, away from eye edges.
        windows = []
        for tap in good:
            if not windows or tap != windows[-1][-1]+1:
                windows.append([])
            windows[-1].append(tap)
        if not windows or max(map(len, windows)) < 3:
            raise RuntimeError('No common stable eye >=3 taps: ' + json.dumps(evidence))
        window = max(windows, key=len)
        tap = window[len(window)//2]
        self.set_taps([tap]*9)
        return {'tap': tap, 'window': window, 'scan': evidence}


class I2C:
    """LiteX open-drain bitbang; stretching and ACK errors are checked."""
    def __init__(self, registers):
        self.r = registers

    def lines(self, scl, sda):
        self.r.write('adc_i2c_w', scl | ((not sda) << 1) | (sda << 2))
        time.sleep(0.00001)
        if scl:
            deadline = time.monotonic()+0.1
            while not self.r.read('adc_i2c_r') & 2:
                if time.monotonic() > deadline:
                    raise TimeoutError('SI570 I2C SCL held low')

    def start(self):
        self.lines(1, 1); self.lines(1, 0); self.lines(0, 0)

    def stop(self):
        self.lines(0, 0); self.lines(1, 0); self.lines(1, 1)

    def send(self, value):
        for bit in range(7, -1, -1):
            v = (value >> bit) & 1
            self.lines(0, v); self.lines(1, v); self.lines(0, v)
        self.lines(0, 1); self.lines(1, 1)
        ack = not self.r.read('adc_i2c_r') & 1
        self.lines(0, 1)
        if not ack:
            raise RuntimeError(f'SI570 I2C NACK for byte {value:#x}')

    def receive(self, last):
        value = 0
        for _ in range(8):
            self.lines(0, 1); self.lines(1, 1)
            value = (value << 1) | (self.r.read('adc_i2c_r') & 1)
            self.lines(0, 1)
        self.lines(0, int(last)); self.lines(1, int(last)); self.lines(0, 1)
        return value

    def read(self, address, register, length):
        try:
            self.start(); self.send(address << 1); self.send(register)
            self.start(); self.send((address << 1) | 1)
            return [self.receive(i == length-1) for i in range(length)]
        finally:
            self.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csr-json', required=True)
    parser.add_argument('--device', default='/dev/uio0')
    parser.add_argument('--si570-address', type=lambda x: int(x, 0), default=0x55)
    parser.add_argument('--tap', type=int)
    parser.add_argument('--external-trigger', action='store_true')
    parser.add_argument('--range', choices=['open', '5V', '0.5V', '0.05V'], default='open')
    parser.add_argument('--output', type=Path, default=Path('adc-capture'))
    args = parser.parse_args()
    r = Registers(args.csr_json, args.device)
    adc = ADC(r)
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'hardware_validated': False, 'result': 'FAIL', 'slot': 'J5 LPC'}
    try:
        adc.initialize()
        result['si570_registers'] = I2C(r).read(args.si570_address, 7, 6)
        hz = adc.sample_rate()
        result['sample_rate_hz'] = hz
        if not 98e6 < hz < 102e6:
            raise RuntimeError(f'Expected factory SI570 100 MHz; measured {hz:g} Hz. '
                               'Do not change oscillator without verifying its configuration.')
        if args.tap is None:
            result['calibration'] = adc.calibrate()
        else:
            adc.set_taps([args.tap]*9)
        # Zero/ones, asymmetric words, all walking ones and walking zeros.
        patterns = [0, 0x3fff, 0x1555, 0x2aaa, 0x1235, 0x2dca]
        patterns += [1 << bit for bit in range(14)]
        patterns += [0x3fff ^ (1 << bit) for bit in range(14)]
        for value in patterns:
            adc.check_pattern(value)
        result['pattern_samples_checked'] = len(patterns)*1024*4
        adc.pattern()
        # CERN SSR routing: range field and 50-ohm termination are separate.
        # Leave termination OFF; use the widest range first when connecting a source.
        ssr = {'open': 0, '5V': 0x45, '0.5V': 0x11, '0.05V': 0x23}[args.range]
        r.write('adc_ssr', sum(ssr << (7*ch) for ch in range(4)))
        time.sleep(0.1)  # relay settling
        words = adc.capture(args.external_trigger)
        raw = b''.join(struct.pack('<4H', *row) for row in words)
        (args.output/'samples.bin').write_bytes(raw)
        with (args.output/'samples.csv').open('w', newline='') as f:
            writer = csv.writer(f); writer.writerow(['sample', 'ch1_code', 'ch2_code', 'ch3_code', 'ch4_code'])
            for i, row in enumerate(words):
                writer.writerow([i] + [((v if v < 32768 else v-65536)//4) for v in row])
        result.update(result='PASS', hardware_validated=True, samples=len(words), range=args.range,
                      analog_calibrated=False)
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        # Disconnect inputs and stop receiver/oscillator; retain evidence on failure.
        r.write('adc_ssr', 0)
        r.write('adc_control', 1)
        r.mem.close()
        (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
