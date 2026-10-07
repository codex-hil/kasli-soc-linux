#!/usr/bin/env python3
"""Capture a ZC706 reboot, log in on UART, and report its DHCP address.

Optional RAM-root boot interrupts U-Boot and loads the recovery initramfs
from SD. No environment save, QSPI write, or SD write is performed.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import time

import serial

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True)
    p.add_argument("--reboot-ssh-address", required=True, type=ipaddress.ip_address)
    p.add_argument("--ram-root", action="store_true")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--seconds", type=int, default=180)
    p.add_argument("--key", type=Path, default=ROOT / "build/ssh/id_ed25519")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    uart = serial.Serial(baudrate=115200, timeout=0.2)
    uart.port, uart.dtr, uart.rts = args.port, False, False
    uart.open()
    transcript = bytearray()
    result = {"hardware": True, "ram_root_requested": args.ram_root,
              "qspi_written": False, "dhcp_address": None}
    ssh = ["ssh", "-i", str(args.key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "UserKnownHostsFile=" + str(args.key.parent / "known_hosts"),
           "root@" + str(args.reboot_ssh_address), "sync; reboot"]
    interrupted = ram_sent = logged_in = False
    next_probe = None
    # U-Boot addresses come from its standard Zynq environment. Fail closed.
    ram_command = " && ".join([
        "load mmc 0:1 ${kernel_addr_r} top.bit",
        "fpga loadb 0 ${kernel_addr_r} ${filesize}",
        "load mmc 0:1 ${fdt_addr_r} zc706.dtb",
        "load mmc 0:1 ${ramdisk_addr_r} rootfs.cpio.gz",
        "setenv initrdsize ${filesize}",
        "load mmc 0:1 ${kernel_addr_r} zImage",
        "setenv bootargs console=ttyPS0,115200 rdinit=/init clk_ignore_unused uio_pdrv_genirq.of_id=generic-uio",
        "bootz ${kernel_addr_r} ${ramdisk_addr_r}:${initrdsize} ${fdt_addr_r}",
    ])
    try:
        with (args.output / "reboot-ssh.log").open("wb") as ssh_log:
            reboot = subprocess.Popen(ssh, stdout=ssh_log, stderr=ssh_log)
            with (args.output / "uart.log").open("wb") as log:
                deadline = time.monotonic() + args.seconds
                while time.monotonic() < deadline:
                    block = uart.read(4096)
                    if block:
                        transcript.extend(block)
                        log.write(block)
                        log.flush()
                    recent = bytes(transcript[-8192:])
                    if args.ram_root and not interrupted and b"Hit any key to stop autoboot" in recent:
                        uart.write(b" ")
                        interrupted = True
                    if args.ram_root and interrupted and not ram_sent and b"Zynq> " in recent:
                        uart.write(ram_command.encode() + b"\n")
                        ram_sent = True
                    if not logged_in and b"zc706-linux login:" in recent:
                        uart.write(b"root\n")
                        logged_in = True
                        next_probe = time.monotonic() + 1
                    if next_probe is not None and time.monotonic() >= next_probe:
                        uart.write(b"ip -4 addr show eth0; cat /proc/mounts; cat /proc/cmdline\n")
                        next_probe = time.monotonic() + 5
                    match = re.search(rb"inet (\d+\.\d+\.\d+\.\d+)/\d+.*?scope global", recent)
                    if match:
                        result["dhcp_address"] = match.group(1).decode()
                        # Capture remaining shell output, including root mount.
                        block = uart.read(4096)
                        transcript.extend(block)
                        log.write(block)
                        break
            reboot.wait(timeout=15)
        for key, pattern in [("spl_banner", b"U-Boot SPL"), ("uboot_banner", b"U-Boot 2026"),
                             ("kernel_banner", b"Linux version 6.18.40"),
                             ("rootfs_login", b"zc706-linux login:")]:
            result[key] = pattern in transcript
        if not result["dhcp_address"]:
            raise RuntimeError("No DHCP address captured; inspect UART log")
        if not all(result[k] for k in ["spl_banner", "uboot_banner", "kernel_banner", "rootfs_login"]):
            raise RuntimeError("Incomplete boot provenance; inspect UART log")
        print(json.dumps(result, indent=2), flush=True)
    finally:
        uart.close()
        (args.output / "boot.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
