#!/usr/bin/env python3
"""Compare selected hardware primitive parameters, not netlist equivalence."""
import argparse
import hashlib
import json
from pathlib import Path

TYPES = ('PS7', 'MMCME2_ADV', 'IDELAYCTRL', 'IDELAYE2', 'ODELAYE2', 'IBUFDS', 'GTXE2_CHANNEL')


def compare(reference, candidate):
    documents = [json.loads(path.read_text())['modules']['top']['cells']
        for path in (reference, candidate)]
    rows = []
    for kind in TYPES:
        old, new = ({name: cell['parameters'] for name, cell in doc.items()
            if cell['type'] == kind} for doc in documents)
        changed = {name: [key for key in sorted(set(old[name]) | set(new[name]))
            if old[name].get(key) != new[name].get(key)]
            for name in sorted(set(old) & set(new)) if old[name] != new[name]}
        rows.append(dict(type=kind, reference_count=len(old), candidate_count=len(new),
            removed=sorted(set(old)-set(new)), added=sorted(set(new)-set(old)),
            parameter_changes=changed, passed=bool(old) and old == new))
    return dict(result='PASS' if all(row['passed'] for row in rows) else 'FAIL',
        hardware_access=False, qualification=False,
        scope='Named primitive parameters only; not connectivity, timing, bitstream or hardware equivalence',
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), primitives=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = compare(args.reference, args.candidate)
    text = json.dumps(report, indent=2)+'\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')
    raise SystemExit(report['result'] != 'PASS')
