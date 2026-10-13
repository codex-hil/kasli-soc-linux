#!/usr/bin/env python3
"""Summarize physical DQ32..39 errors from fixed-setting DFI diagnostics."""
import argparse
import gzip
import json
import re
from pathlib import Path


def analyze(text):
    rows = 0
    seeds = set()
    bits = [dict(dq=32+i, samples=0, errors=0, expected_ones=0, actual_ones=0) for i in range(8)]
    for line in text.splitlines():
        if 'DQ_DETAIL seed=' not in line:
            continue
        match = re.search(r'DQ_DETAIL seed=(\d+) phase=([0-3]) expected=([0-9a-f]{4}) actual=([0-9a-f]{4})$',line)
        if not match:
            raise ValueError('Malformed DQ detail row')
        seed,phase,expected,actual = match.groups()
        seeds.add(int(seed));rows += 1
        for want,got in zip(bytes.fromhex(expected),bytes.fromhex(actual)):
            for i,bit in enumerate(bits):
                e,a=(want>>i)&1,(got>>i)&1
                bit['samples']+=1;bit['errors']+=e!=a
                bit['expected_ones']+=e;bit['actual_ones']+=a
    if not rows:
        raise ValueError('No DQ detail samples')
    return dict(qualification=False,rows=rows,seeds=sorted(seeds),bits=bits,
        limitation='Fixed diagnostic settings may be untrained on golden. Error distribution alone does not establish a physical pin fault or write/read causality.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();text=gzip.open(a.log,'rt').read() if a.log.suffix=='.gz' else a.log.read_text()
    result=analyze(text);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('DQ errors:',[x['errors'] for x in result['bits']])


if __name__=='__main__':main()
