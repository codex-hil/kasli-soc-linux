#!/usr/bin/env python3
"""Validate and summarize complete per-DQ read eye scans (not qualification)."""
import argparse
import gzip
import json
import re
from pathlib import Path


def analyze(text):
    points={}
    for line in text.splitlines():
        if 'DQ_EYE slip=' not in line:continue
        m=re.fullmatch(r'DQ_EYE slip=(\d+) delay=(\d+) samples=(\d+) errors=([0-9,]+)',line)
        if not m:raise ValueError('Malformed eye point')
        slip,delay,samples=map(int,m.groups()[:3]);errors=list(map(int,m[4].split(',')))
        if slip not in range(8) or delay not in range(32) or samples<=0 or len(errors)!=8 or any(x<0 or x>samples for x in errors):raise ValueError('Invalid eye point')
        if (slip,delay) in points:raise ValueError('Duplicate eye point')
        points[slip,delay]=dict(samples=samples,errors=errors)
    if set(points)!={(s,d) for s in range(8) for d in range(32)}:raise ValueError('Incomplete eye scan')
    return dict(qualification=False,points=256,
        samples_per_bit_per_point=sorted({v['samples'] for v in points.values()}),
        slips=[dict(slip=s,common_passing_taps=[d for d in range(32) if not any(points[s,d]['errors'])],
                    lanes=[dict(dq=32+b,passing_taps=[d for d in range(32) if points[s,d]['errors'][b]==0],
                                minimum_errors=min(points[s,d]['errors'][b] for d in range(32))) for b in range(8)]) for s in range(8)],
        limitation='Fixed write-DQ/DQS settings; finite samples. Zero error taps are diagnostic candidates, not DDR qualification.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();text=gzip.open(a.log,'rt').read() if a.log.suffix=='.gz' else a.log.read_text();r=analyze(text)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print('Common passing settings:',sum(len(s['common_passing_taps']) for s in r['slips']))
    for s in r['slips']:
        print('slip',s['slip'],'per-DQ passing taps:',[len(l['passing_taps']) for l in s['lanes']])


if __name__=='__main__':main()
