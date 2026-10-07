#!/usr/bin/env python3
"""Grant this host user access to the explicitly selected ZC706 USB pair."""
import argparse
import os
from pathlib import Path
import pwd
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--jtag-serial', default='210251841109')
p.add_argument('--user', default='codex-hil')
args = p.parse_args()
pwd.getpwnam(args.user)
uart = Path('/dev/serial/by-id/usb-Silicon_Labs_CP2103_USB_to_UART_Bridge_Controller_0001-if00-port0').resolve(strict=True)
if not uart.name.startswith('ttyUSB'):
    raise RuntimeError('unexpected UART device')
matches = []
for usb in Path('/sys/bus/usb/devices').iterdir():
    try:
        if ((usb / 'serial').read_text().strip() == args.jtag_serial
                and (usb / 'idVendor').read_text().strip() == '0403'
                and (usb / 'idProduct').read_text().strip() == '6014'):
            bus = int((usb / 'busnum').read_text())
            dev = int((usb / 'devnum').read_text())
            matches.append(Path(f'/dev/bus/usb/{bus:03}/{dev:03}'))
    except FileNotFoundError:
        pass
if len(matches) != 1:
    raise RuntimeError('selected Digilent JTAG adapter not uniquely found')
command = ['setfacl', '-m', f'u:{args.user}:rw', str(uart), str(matches[0])]
print(' '.join(command), flush=True)
if os.geteuid() != 0:
    raise SystemExit('Run this script through sudo; no permissions changed.')
subprocess.run(command, check=True)
