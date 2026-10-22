#!/usr/bin/env python3
"""Offline raw PHY frame comparison and independent Ethernet FCS calculation."""
import argparse
import binascii
import json
from pathlib import Path

PREAMBLE = b'\x55' * 7 + b'\xd5'
MAC = bytes.fromhex('02c0de706001')
BODY = MAC + MAC + b'\x88\xb5' + bytes(n ^ 0xa5 for n in range(64))
EXPECTED = PREAMBLE + BODY + binascii.crc32(BODY).to_bytes(4, 'little')


def analyze(capture):
    data = bytes.fromhex(capture.get('data_hex', ''))
    complete = (capture.get('done') == 1 and capture.get('overflow') == 0
                and not capture.get('truncated', False)
                and len(data) == capture.get('length')
                and 0 < len(data) <= capture.get('capacity', 0))
    result = dict(complete=complete, length=capture.get('length'),
                  error=capture.get('error'), overflow=capture.get('overflow'))
    if not complete:
        return result, data
    result['preamble_valid'] = data.startswith(PREAMBLE)
    result['matches_expected_test_frame'] = data == EXPECTED
    if result['preamble_valid'] and len(data) >= 26:
        body, fcs = data[8:-4], data[-4:]
        expected_fcs = binascii.crc32(body).to_bytes(4, 'little')
        result.update(fcs=fcs.hex(), expected_fcs=expected_fcs.hex(),
                      fcs_valid=fcs == expected_fcs,
                      target_mac=body[:6].hex(':'), sender_mac=body[6:12].hex(':'),
                      ethernet_type=f'0x{int.from_bytes(body[12:14], "big"):04x}',
                      payload_bytes=len(body)-14)
    else:
        result['fcs_valid'] = None
    return result, data


def compare(report):
    raw = report.get('raw_phy_capture', {})
    frames, data = {}, {}
    for direction in ('tx', 'rx'):
        frames[direction], data[direction] = analyze(raw.get(direction, {}))
    complete = all(v['complete'] for v in frames.values())
    result = dict(hardware_access=False, captures=frames, both_complete=complete,
                  identical=None, result='INCOMPLETE_CAPTURE')
    if complete:
        result['identical'] = data['tx'] == data['rx']
        result['different_byte_count'] = sum(a != b for a, b in zip(data['tx'], data['rx'])) + abs(len(data['tx'])-len(data['rx']))
        result['first_differences'] = [dict(offset=i, tx=a, rx=b)
            for i, (a, b) in enumerate(zip(data['tx'], data['rx'])) if a != b][:16]
        clean = all(v.get('fcs_valid') is True and v['error'] == 0 for v in frames.values())
        result['result'] = 'IDENTICAL_VALID_FCS' if result['identical'] and clean else 'FRAME_DIFFERENCE_OR_ERROR'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(compare(json.loads(args.probe.read_text())), indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')
