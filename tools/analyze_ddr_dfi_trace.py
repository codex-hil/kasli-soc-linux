#!/usr/bin/env python3
"""Summarize sampled raw DFI training data for the ZC706 64-bit DDR PHY."""
import argparse
import collections
import json
import re
from pathlib import Path

PATTERN = re.compile(r'DFI_TRACE call=(\d+) module=4 seed=(\d+) phase=(\d+) select=([0-9a-f]+) expected=([0-9a-f]+) actual=([0-9a-f]+)')


def analyze(log):
    rows = []
    values = [collections.Counter() for _ in range(8)]
    errors = [0] * 8
    matches = [0] * 8
    for line in log.splitlines():
        if 'DFI_TRACE' not in line:
            continue
        match = PATTERN.search(line)
        if not match:
            raise ValueError('Malformed DFI trace: ' + line)
        call, seed, phase, select, expected, actual = match.groups()
        expected, actual = bytes.fromhex(expected), bytes.fromhex(actual)
        if len(expected) != 16 or len(actual) != 16:
            raise ValueError('Expected 16 bytes per DDR DFI phase')
        for lane in range(8):
            for offset in (lane, lane + 8):
                values[lane][actual[offset]] += 1
                difference = expected[offset] ^ actual[offset]
                errors[lane] += difference.bit_count()
                matches[lane] += difference == 0
        rows.append(dict(call=int(call), seed=int(seed), phase=int(phase), select=int(select,16)))
    if not rows:
        raise ValueError('No actual DFI trace rows')
    return dict(qualification=False, sampled_rows=len(rows),
        note='Samples include intentionally untrained scan settings; mismatch counts do not qualify memory.',
        calls=sorted(set(r['call'] for r in rows)), select_values=sorted(set(r['select'] for r in rows)),
        lanes=[dict(lane=i, matched_bytes=matches[i], bit_errors=errors[i],
                    actual_histogram={f'{k:02x}':v for k,v in sorted(values[i].items())}) for i in range(8)])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=analyze(a.log.read_text())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Sampled rows:',result['sampled_rows'],'byte-four distinct values:',len(result['lanes'][4]['actual_histogram']))


if __name__=='__main__':main()
