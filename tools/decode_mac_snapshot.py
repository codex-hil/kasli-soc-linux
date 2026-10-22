#!/usr/bin/env python3
"""Decode frozen MAC headers from sfp_probe JSON without accessing hardware."""
import argparse
import json
from pathlib import Path


def decode(report):
    status = report['status']
    captures = {}
    for direction in ('tx', 'rx'):
        prefix = 'mac_status_' + direction + '_capture_'
        if prefix + 'valid' not in status:
            captures[direction] = {'available': False}
            continue
        valid = status[prefix + 'valid'] == 1
        entry = dict(available=True, valid=valid)
        if valid:
            for field in ('target', 'sender'):
                value = status[prefix + field + '_lo'] | (status[prefix + field + '_hi'] << 32)
                entry[field + '_mac'] = ':'.join(f'{b:02x}' for b in value.to_bytes(6, 'big'))
            entry.update(ethernet_type=f"0x{status[prefix+'ethernet_type']:04x}",
                         payload_bytes=status[prefix + 'payload_bytes'],
                         error=status[prefix + 'error'])
        captures[direction] = entry
    tx, rx = captures['tx'], captures['rx']
    complete = tx.get('valid', False) and rx.get('valid', False)
    fields = ('target_mac', 'sender_mac', 'ethernet_type', 'payload_bytes', 'error')
    return dict(hardware_access=False, captures=captures,
                both_captured=complete,
                headers_match=all(tx[k] == rx[k] for k in fields) if complete else None,
                scope='Frozen header comparison only; payload bytes were not captured')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(decode(json.loads(args.probe.read_text())), indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')
