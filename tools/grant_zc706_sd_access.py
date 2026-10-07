#!/usr/bin/env python3
"""Grant codex-hil access only to the identified 32 GB test SD card."""
import json
import os
from pathlib import Path
import subprocess

CARD = Path('/dev/disk/by-id/usb-Generic_MassStorageClass_000000001536-0:0')
device = CARD.resolve(strict=True)
report = json.loads(subprocess.check_output(
    ['lsblk', '-b', '-J', '-o', 'PATH,SIZE,TYPE,TRAN,SERIAL,MOUNTPOINTS', str(device)],
    text=True))['blockdevices'][0]
if (report['type'] != 'disk' or report['tran'] != 'usb'
        or report['serial'] != '000000001536' or report['size'] != 31914983424):
    raise SystemExit('Selected device is not the expected 32 GB USB test card.')
def mounted(node):
    return any(node.get('mountpoints') or []) or any(mounted(c) for c in node.get('children', []))
if mounted(report):
    raise SystemExit('Card is mounted; unmount it first.')
command = ['setfacl', '-m', 'u:codex-hil:rw', str(device)]
print('Verified test card:', device, report['size'], 'bytes', flush=True)
if os.geteuid() != 0:
    raise SystemExit('Run through sudo; no permissions changed.')
subprocess.run(command, check=True)
