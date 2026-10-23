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
    if r.map["constants"].get("sfp_refclk_source") == "fclk":
        return dict(source="fclk", si5324_programmed=False)
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


def drp_read(r, address):
    if r.read("sfp_status_drp_busy"):
        raise RuntimeError("GTX DRP was already busy")
    r.write("sfp_status_drp_address", address)
    r.write("sfp_status_drp_command", 0)  # A write strobe requests a read; bit 0 enables writes.
    deadline = time.monotonic()+1
    while r.read("sfp_status_drp_busy"):
        if time.monotonic() > deadline:
            raise TimeoutError(f"GTX DRP read 0x{address:03x} did not acknowledge")
        time.sleep(.001)
    return r.read("sfp_status_drp_read_data")


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


def loopback_test(r, count, mode="pma", observation=None, diagnostic_burst=0, warmup=0, capture_startup=False):
    if r.read("sfp_status_signature") != 0x53465031:
        raise RuntimeError("Requires SFP ABI 1 gateware")
    # Near-end PMA loopback keeps the full software PCS/8b10b, MAC and CRC path.
    selection = {"pma": 2, "pcs": 1}[mode]
    startup_directions = ("rx_cdc", "crc_input", "crc_output") if capture_startup else ()
    if capture_startup:
        if warmup:
            raise ValueError("Startup capture must not be combined with warmup")
        required = ["mac_status_" + d + "_raw_arm" for d in startup_directions]
        if not all(name in r.map["csr_registers"] for name in required):
            raise RuntimeError("Startup capture requires all three sys-domain RX probes")
        if observation is not None:
            observation["startup"] = dict(before=status(r),
                directions=list(startup_directions),
                scope="First complete frame per sys-domain probe; not a continuous trace")
        for name in required:
            r.write(name, 1)
        deadline = time.monotonic() + 1
        while not all(r.read(name[:-3] + "armed") or r.read(name[:-3] + "done") for name in required):
            if time.monotonic() > deadline:
                raise TimeoutError("Startup sys-domain probes did not arm")
            time.sleep(.001)
    r.write("sfp_status_control", 8 | selection | 16)
    time.sleep(.01)
    r.write("sfp_status_control", 8 | selection)
    deadline = time.monotonic()+10
    while r.read("sfp_status_status") & 63 != 63:
        if time.monotonic() > deadline:
            raise TimeoutError(f"GTX/PCS loopback did not lock: {status(r)}")
        time.sleep(.01)
    if capture_startup and observation is not None:
        observation["startup"]["after_lock"] = status(r)
    if warmup:
        warmup_before = status(r)
        for n in range(warmup):
            r.write("packet_test_start", 1)
            deadline = time.monotonic() + 1
            while (r.read("packet_test_tx_frames") - warmup_before["packet_test_tx_frames"]) & 0xffffffff != n+1:
                if time.monotonic() > deadline:
                    raise TimeoutError("Warmup TX did not complete")
                time.sleep(.001)
            time.sleep(.02)
        if observation is not None:
            observation["warmup"] = dict(frames=warmup, before=warmup_before, after=status(r))
    # Snapshot the first complete MAC frame after explicit arming, if present.
    # No clear-on-read, no dependence on repeated MMIO polling timing.
    raw_directions = []
    for direction in ("tx", "rx", "rx_cdc", "crc_input", "crc_output"):
        prefix = "mac_status_" + direction + "_raw_"
        if prefix + "arm" in r.map["csr_registers"] and direction not in startup_directions:
            r.write(prefix + "arm", 1)
            raw_directions.append(prefix)
    deadline = time.monotonic() + 1
    while raw_directions and not all(r.read(p + "armed") or r.read(p + "done") for p in raw_directions):
        if time.monotonic() > deadline:
            raise TimeoutError("Raw PHY capture arm did not cross the clock domain")
        time.sleep(.001)
    for direction in ("tx", "rx"):
        arm = "mac_status_" + direction + "_capture_arm"
        if arm in r.map["csr_registers"]:
            r.write(arm, 1)
    before = status(r)
    if observation is not None:
        observation.update(mode=mode, before=before, diagnostic_burst=diagnostic_burst)
    count = diagnostic_burst or count
    counter = "packet_test_tx_frames" if diagnostic_burst else "packet_test_rx_frames"
    for n in range(count):
        r.write("packet_test_start", 1)
        deadline = time.monotonic()+1
        while (r.read(counter) - before[counter]) & 0xffffffff != n+1:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Loopback packet {n} not received: {status(r)}")
            time.sleep(.001)
        if diagnostic_burst:
            time.sleep(.02)
    if diagnostic_burst:
        deadline = time.monotonic() + 1
        while (r.read("packet_test_rx_frames") - before["packet_test_rx_frames"]) & 0xffffffff != count:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Diagnostic burst sent {count} frames but RX did not match: {status(r)}")
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
    return {"result": "PASS", "mode": mode, "frames": count, "payload_bytes": 64,
            "before": before, "after": after, "user_clock_hz": frequencies}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csr-json", required=True)
    p.add_argument("--device", default="/dev/uio0")
    p.add_argument("--identify-only", action="store_true")
    p.add_argument("--init-clock", action="store_true")
    p.add_argument("--loopback", type=int, default=0)
    p.add_argument("--loopback-mode", choices=("pma", "pcs"), default="pma")
    p.add_argument("--diagnostic-burst", type=int, choices=range(0,9), default=0, help="Send up to8 frames using TX completion before checking RX")
    p.add_argument("--loopback-warmup",type=int,choices=range(0,9),default=0,help="Explicit mode-transition warmup, recorded separately from qualification")
    p.add_argument("--capture-startup", action="store_true", help="Arm sys-domain RX probes before mode/reset; no warmup")
    p.add_argument("--external", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if (a.diagnostic_burst or a.loopback_warmup) and not a.loopback:
        p.error("Diagnostic burst requires loopback")
    if a.capture_startup and (not a.loopback or a.loopback_warmup):
        p.error("Startup capture requires loopback without warmup")
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
            if "sfp_status_drp_address" in r.map["csr_registers"]:
                # UG476 table D-2: CPLL configuration/dividers, output dividers, RX CDR.
                result["drp"] = {f"0x{x:03x}": drp_read(r, x)
                    for x in [0x5b, 0x5c, 0x5d, 0x5e, 0x5f, 0x88, *range(0xa8, 0xad)]}
            if a.init_clock:
                result["clock"] = initialize_clock(r, bus)
            if a.loopback:
                result["loopback_observation"] = {}
                result["loopback"] = loopback_test(r, a.loopback, a.loopback_mode, result["loopback_observation"], a.diagnostic_burst, a.loopback_warmup, a.capture_startup)
            if a.external:
                r.write("sfp_status_control", 8 | 16)
                time.sleep(.01); r.write("sfp_status_control", 8)
                # Copper SFP PHY negotiation can finish after the PCS reset.
                # Do not classify a two-second snapshot as a permanent failure.
                start = time.monotonic()
                while r.read("sfp_status_status") & 63 != 63 and time.monotonic()-start < 30:
                    time.sleep(.2)
                result["external_link_wait_seconds"] = time.monotonic()-start
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
        observation = result.get("loopback_observation", {})
        if "before" in observation and "status" in result:
            observation["after"] = result["status"]
            names = ("mac_status_tx_frames", "mac_status_rx_frames",
                "mac_status_crc_errors", "mac_status_preamble_errors",
                "sfp_status_clock_faults", "packet_test_tx_frames",
                "packet_test_rx_frames", "packet_test_errors")
            observation["counter_deltas"] = {name:
                (result["status"][name] - observation["before"][name]) & 0xffffffff
                for name in names if name in result["status"] and name in observation["before"]}
        raw = {}
        for direction in ("tx", "rx", "rx_cdc", "crc_input", "crc_output"):
            prefix = "mac_status_" + direction + "_raw_"
            if prefix + "done" not in r.map["csr_registers"]:
                continue
            capture = {k: r.read(prefix+k) for k in ("done", "length", "error", "overflow", "capacity")}
            data = []
            if capture["done"]:
                for address in range(min(capture["length"], capture["capacity"])):
                    r.write(prefix + "address", address)
                    data.append(r.read(prefix + "data") & 255)
            capture["data_hex"] = bytes(data).hex()
            capture["truncated"] = capture["length"] > capture["capacity"]
            raw[direction] = capture
        if raw:
            result["raw_phy_capture"] = raw
        r.mem.close()
        a.output.write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
