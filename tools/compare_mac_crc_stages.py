#!/usr/bin/env python3
"""Compare passive RX stage bytes, without assuming a CRC flag implies corruption."""
import argparse
import binascii
import json
from pathlib import Path
from compare_phy_frames import analyze


def compare(report):
    captures = report.get('raw_phy_capture', {})
    states, data = {}, {}
    for name in ('rx', 'rx_cdc', 'crc_input', 'crc_output'):
        states[name], data[name] = analyze(captures.get(name, {}))
    rows = []
    for name, reference, start, end in (
            ('rx_cdc', 'rx', 0, None),
            ('crc_input', 'rx_cdc', 8, None),
            ('crc_output', 'crc_input', 0, -4)):
        complete = states[name]['complete'] and states[reference]['complete']
        row = dict(stage=name, reference=reference, complete=complete,
                   error=states[name].get('error'))
        if complete:
            expected, actual = data[reference][start:end], data[name]
            row.update(expected_length=len(expected), actual_length=len(actual),
                       identical=actual == expected,
                       first_differences=[dict(offset=i, expected=a, actual=b)
                           for i, (a, b) in enumerate(zip(expected, actual)) if a != b][:16])
        rows.append(row)
    complete = all(row['complete'] for row in rows)
    result = 'INCOMPLETE_STAGE_CAPTURE'
    if complete:
        result = 'BYTE_DIFFERENCE' if any(not row['identical'] for row in rows) else (
            'EXPECTED_BYTES_WITH_ERROR_FLAG' if any(row['error'] for row in rows)
            else 'EXPECTED_STAGE_BYTES')
    crc_valid = None
    if states['crc_input']['complete'] and len(data['crc_input']) >= 18:
        body = data['crc_input']
        crc_valid = binascii.crc32(body[:-4]).to_bytes(4, 'little') == body[-4:]
    return dict(result=result, hardware_access=False, stages=rows,
                raw_rx_fcs_valid=states['rx'].get('fcs_valid'),
                crc_checker_input_fcs_valid=crc_valid,
                scope='Byte comparisons at observed handshakes, not internal CRC state or bit equivalence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(compare(json.loads(args.probe.read_text())), indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')
