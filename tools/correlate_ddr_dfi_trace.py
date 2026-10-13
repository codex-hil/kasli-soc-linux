#!/usr/bin/env python3
"""Test beat rotation/lane substitution against complete sampled DFI bursts."""
import argparse
import gzip
import json
from pathlib import Path
from analyze_ddr_dfi_trace import PATTERN


def correlate(text):
    bursts = {}
    for line in text.splitlines():
        if 'DFI_TRACE' not in line:
            continue
        match = PATTERN.search(line)
        if not match:
            raise ValueError('Malformed trace')
        call, seed, phase, select, expected, actual = match.groups()
        call, phase = int(call), int(phase)
        expected, actual = bytes.fromhex(expected), bytes.fromhex(actual)
        if len(expected) != 16 or len(actual) != 16 or phase not in range(4):
            raise ValueError('Expected four 16-byte DFI phases')
        burst = bursts.setdefault(call, dict(seed=int(seed), phases={}))
        if burst['seed'] != int(seed) or phase in burst['phases']:
            raise ValueError('Conflicting burst phases')
        burst['phases'][phase] = (expected, actual)
    rows = []
    incomplete = []
    for call, burst in sorted(bursts.items()):
        if set(burst['phases']) != set(range(4)):
            incomplete.append(call)
            continue
        expected = [[burst['phases'][p][0][lane+edge*8] for p in range(4) for edge in range(2)] for lane in range(8)]
        actual = [burst['phases'][p][1][4+edge*8] for p in range(4) for edge in range(2)]
        hypotheses = []
        for lane in range(8):
            for shift in range(8):
                for invert in (0, 255):
                    errors = sum((actual[i] ^ expected[lane][(i+shift)%8] ^ invert).bit_count() for i in range(8))
                    hypotheses.append(dict(source_lane=lane, beat_shift=shift, inverted=bool(invert), bit_errors=errors))
        same_lane = min((x for x in hypotheses if x['source_lane']==4), key=lambda x:x['bit_errors'])
        best = min(hypotheses,key=lambda x:x['bit_errors'])
        per_bit = []
        for bit in range(8):
            choices = [(sum(((actual[i] ^ expected[4][(i+s)%8])>>bit & 1) ^ inv for i in range(8)),s,inv)
                       for s in range(8) for inv in (0,1)]
            errors,shift,invert = min(choices)
            per_bit.append(dict(dq=32+bit, bit_errors=errors, beat_shift=shift, inverted=bool(invert)))
        rows.append(dict(call=call, seed=burst['seed'], unshifted_bit_errors=sum((a^b).bit_count() for a,b in zip(actual,expected[4])),
                         best_same_lane=same_lane,best_any_lane=best,independent_bit_rotations=per_bit))
    if not rows:
        raise ValueError('No complete bursts')
    return dict(hardware_access=False, qualification=False, complete_bursts=len(rows), incomplete_calls=incomplete,
        exact_same_lane_rotation_bursts=sum(r['best_same_lane']['bit_errors']==0 for r in rows),
        exact_any_lane_rotation_bursts=sum(r['best_any_lane']['bit_errors']==0 for r in rows),
        bursts=rows, limitation='Fits over eight sampled beats can match by chance. Scan settings differ; this cannot distinguish write from read faults or qualify DDR.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    text=gzip.open(a.log,'rt').read() if a.log.suffix=='.gz' else a.log.read_text()
    r=correlate(text)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print('Bursts:',r['complete_bursts'],'exact same-lane fits:',r['exact_same_lane_rotation_bursts'],
          'exact any-lane fits:',r['exact_any_lane_rotation_bursts'])


if __name__=='__main__':main()
