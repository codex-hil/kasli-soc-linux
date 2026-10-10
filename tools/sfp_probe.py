#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Linux GP0 diagnostics for the ZC706 SFP target; volatile clock settings only."""
import argparse
import ctypes
import json
import mmap
import os
from pathlib import Path
import time
from fmc_adc import I2C


class Registers:
    def __init__(self, path, device="/dev/uio0"):
        self.map = json.loads(Path(path).read_text())
        region = self.map["memories"]["csr"]
        self.base = region["base"]
        uio = Path(device).name.startswith("uio")
        if uio:
            sysfs = Path("/sys/class/uio")/Path(device).name/"maps/map0"
            if int((sysfs/"addr").read_text(), 0) != self.base or int((sysfs/"size").read_text(), 0) < region["size"]:
                raise RuntimeError("UIO does not cover the CSR region")
        fd = os.open(device, os.O_RDWR | os.O_SYNC)
        try:
            self.mem = mmap.mmap(fd, region["size"], offset=0 if uio else self.base)
        finally:
            os.close(fd)
        if self.read("probe_signature") != 0x4b534f43:
            raise RuntimeError("PL signature mismatch")

    def word(self, name):
        # Reuse the tested bitbang I2C implementation with board CSR aliases.
        name = name.replace("adc_i2c_", "board_i2c_")
        offset = self.map["csr_registers"][name]["addr"] - self.base
        if offset < 0 or offset & 3 or offset+4 > len(self.mem):
            raise ValueError("Unaligned/out-of-range CSR")
        return ctypes.c_uint32.from_buffer(self.mem, offset)

    def read(self, name):
        return self.word(name).value

    def write(self, name, value):
        if not 0 <= value <= 0xffffffff:
            raise ValueError("CSR value outside unsigned word")
        self.word(name).value = value


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

    def reg_write(self, address, reg, value):
        try:
            self.start(); self.send(address << 1); self.send(reg); self.send(value)
        finally:
            self.stop()


def identify_module(bus):
    saved = bus.raw_read(0x74)
    try:
        # UG954 table 1-25: SFP on mux channel 0, Si5324 on channel 4.
        bus.raw_write(0x74, 1 << 0)
        raw = bytes(bus.read(0x50, 0, 96))
        if sum(raw[:63]) & 255 != raw[63] or sum(raw[64:95]) & 255 != raw[95]:
            raise RuntimeError("SFP EEPROM checksum mismatch")
        return {"eeprom_hex": raw.hex(), "identifier": raw[0],
            "vendor": raw[20:36].decode("ascii", errors="replace").strip(),
            "part": raw[40:56].decode("ascii", errors="replace").strip(),
            "serial": raw[68:84].decode("ascii", errors="replace").strip(),
            "ethernet_compliance": raw[6], "nominal_mbps": raw[12]*100,
            "connector": raw[2]}
    finally:
        bus.raw_write(0x74, saved)


def initialize_clock(r, bus):
    # Same logical divider profile and register mapping as golden ARTIQ
    # artiq-zynq/src/runtime/src/rtio_clocking.rs: Int_125, Si5324 crystal input.
    r.write("sfp_status_control", 16)  # PHY reset, Si5324 reset asserted.
    time.sleep(.001)
    r.write("sfp_status_control", 24)
    time.sleep(.01)
    saved = bus.raw_read(0x74)
    try:
        bus.raw_write(0x74, 1 << 4)
        def read(reg):
            return bus.read(0x68, reg, 1)[0]
        def write(reg, val):
            bus.reg_write(0x68, reg, val)
        def rmw(reg, mask, value):
            write(reg, (read(reg) & mask) | value)
        ident = bus.read(0x68, 134, 2)
        if (ident[0] << 8) | ident[1] != 0x182:
            raise RuntimeError(f"Unexpected Si5324 product ID: {ident}")
        rmw(0, 0xff, 0x40)  # free run, crystal on CKIN2
        rmw(2, 0x0f, 4 << 4)
        rmw(21, 0xfe, 0)
        rmw(3, 0x2f, 0x50)
        rmw(4, 0x3f, 0)
        rmw(6, 0xc0, 0x3f)
        write(25, (10-4) << 5)
        for first, val in [(31, 4-1), (34, 4-1), (40, ((10-4) << 21) | (19972-1)),
                           (43, 4565-1), (46, 4565-1)]:
            for n in range(3):
                write(first+n, (val >> (16-8*n)) & 255)
        rmw(137, 0xff, 1)
        rmw(136, 0xff, 0x40)
        # LOL can read zero immediately after ICAL is requested, before
        # calibration starts. Require ICAL clear and a stable lock interval.
        deadline = time.monotonic()+60
        stable_since = None
        while True:
            now = time.monotonic()
            ready = not (read(136) & 0x40) and not (read(130) & 1)
            stable_since = (stable_since if stable_since is not None else now) if ready else None
            if stable_since is not None and now-stable_since >= .2:
                break
            if now > deadline:
                raise TimeoutError("Si5324 calibration/lock did not settle")
            time.sleep(.05)
        return {"product_id": "0x0182", "reference_hz": 125000000,
            "status_128_130": bus.read(0x68, 128, 3),
            "divider_registers_25_48": bus.read(0x68, 25, 24), "persistent_writes": False}
    finally:
        bus.raw_write(0x74, saved)
        r.write("sfp_status_control", 8)


def decode_gray(word):
    value = word
    while word:
        word >>= 1
        value ^= word
    return value


def status(r):
    names = [n for n in r.map["csr_registers"] if n.startswith(("sfp_status_", "packet_test_", "mac_status_"))]
    return {n: r.read(n) for n in names}


def clock_rates(r):
    names = [n for n in ("sfp_status_si_ref_count", "sfp_status_gt_ref_count",
                         "sfp_status_rx_count", "sfp_status_tx_count")
             if n in r.map["csr_registers"]]
    initial = [decode_gray(r.read(n)) for n in names]
    start = time.monotonic()
    time.sleep(.2)
    final = [decode_gray(r.read(n)) for n in names]
    elapsed = time.monotonic()-start
    return {n: ((b-a) & 0xffffffff)/elapsed for n, a, b in zip(names, initial, final)}


def loopback_test(r, count):
    if r.read("sfp_status_signature") != 0x53465031:
        raise RuntimeError("Requires SFP ABI 1 gateware")
    # Near-end PMA loopback keeps the full software PCS/8b10b, MAC and CRC path.
    r.write("sfp_status_control", 8 | 2 | 16)
    time.sleep(.01)
    r.write("sfp_status_control", 8 | 2)
    deadline = time.monotonic()+10
    while r.read("sfp_status_status") & 63 != 63:
        if time.monotonic() > deadline:
            raise TimeoutError(f"GTX/PCS loopback did not lock: {status(r)}")
        time.sleep(.01)
    before = status(r)
    for n in range(count):
        r.write("packet_test_start", 1)
        deadline = time.monotonic()+1
        while (r.read("packet_test_rx_frames") - before["packet_test_rx_frames"]) & 0xffffffff != n+1:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Loopback packet {n} not received: {status(r)}")
            time.sleep(.001)
    after = status(r)
    names = ("sfp_status_rx_count", "sfp_status_tx_count")
    t0 = time.monotonic()
    initial = [decode_gray(r.read(n)) for n in names]
    time.sleep(.1)
    final = [decode_gray(r.read(n)) for n in names]
    elapsed = time.monotonic()-t0
    frequencies = {n: ((b-a) & 0xffffffff)/elapsed for n, a, b in zip(names, initial, final)}
    if any(abs(f-125e6) > 125e6*.02 for f in frequencies.values()):
        raise RuntimeError(f"GTX user clock frequency is not 125 MHz: {frequencies}")
    for name in ("packet_test_errors", "mac_status_crc_errors", "mac_status_preamble_errors"):
        if name in before and after[name] != before[name]:
            raise RuntimeError(f"Loopback error counter incremented: {name}")
    if (after["packet_test_tx_frames"]-before["packet_test_tx_frames"]) & 0xffffffff != count:
        raise RuntimeError("TX count mismatch")
    return {"result": "PASS", "frames": count, "payload_bytes": 64,
            "before": before, "after": after, "user_clock_hz": frequencies}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csr-json", required=True)
    p.add_argument("--device", default="/dev/uio0")
    p.add_argument("--identify-only", action="store_true")
    p.add_argument("--init-clock", action="store_true")
    p.add_argument("--loopback", type=int, default=0)
    p.add_argument("--external", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    r = Registers(a.csr_json, a.device); bus = BoardI2C(r)
    result = {"result": "FAIL", "hardware_validated": False}
    try:
        try:
            result["module"] = identify_module(bus)
        except RuntimeError as e:
            result["module_error"] = str(e)
        if not a.identify_only:
            if r.map["constants"].get("sfp_abi") != 1:
                raise RuntimeError("Requires SFP target CSR map")
            if a.init_clock:
                result["clock"] = initialize_clock(r, bus)
            if a.loopback:
                result["loopback"] = loopback_test(r, a.loopback)
            if a.external:
                r.write("sfp_status_control", 8 | 16)
                time.sleep(.01); r.write("sfp_status_control", 8)
                time.sleep(2)
            result["status"] = status(r)
            result["clock_rates_hz"] = clock_rates(r)
        result.update(result="PASS" if not a.identify_only or "module" in result else "NOT_PRESENT",
                      hardware_validated=not a.identify_only or "module" in result)
    except Exception as e:
        result["error"] = str(e)
        result["status"] = status(r)
        result["clock_rates_hz"] = clock_rates(r)
        raise
    finally:
        r.mem.close()
        a.output.write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
