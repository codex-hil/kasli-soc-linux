#!/usr/bin/env python3
"""Apply reference-measured HR termination features to an isolated DB overlay."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def prepare(original):
    mapping_file = ROOT/'patches/prjxray-hr-diff-term.json'
    mapping = json.loads(mapping_file.read_text())
    if not mapping['repeated_baseline_identical'] or not mapping['all_on_union_verified']:
        raise RuntimeError('Unverified termination reference')
    overlay = ROOT/'build/zc706-adc/termination-db/zynq7'
    overlay.mkdir(parents=True, exist_ok=True)
    patched = {feature.split('.')[0].lower() for feature in mapping['features']}
    for file in original.iterdir():
        dest = overlay/file.name
        if file.name not in {f'segbits_{tile}.db' for tile in patched}:
            if dest.is_symlink() and dest.readlink() != file.resolve():
                temporary = dest.with_suffix('.link-tmp')
                temporary.unlink(missing_ok=True)
                temporary.symlink_to(file.resolve())
                temporary.replace(dest)
            elif not dest.exists() and not dest.is_symlink():
                dest.symlink_to(file.resolve())
            continue
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != mapping['source_db_sha256'][file.name]:
            raise RuntimeError('Termination source DB changed; re-audit '+file.name)
        content = file.read_text()
        source_features = dict(line.split(' ', 1) for line in content.splitlines() if line)
        for feature, alias in mapping['input_only_aliases'].items():
            if feature.split('.')[0].lower() not in file.name:
                continue
            if feature in source_features:
                raise RuntimeError('Upstream already defines '+feature)
            source = source_features[alias['source_feature']].split()
            omit = alias['omit_bits']
            expected = {'!'+bit for bit in mapping['features'][feature.split('.')[0]+'.DIFF.DIFF_TERM']}
            if set(omit) != expected or not set(omit).issubset(source):
                raise RuntimeError('Input-only alias must relax exactly the measured termination bits')
            content += feature+' '+' '.join(bit for bit in source if bit not in omit)+'\n'
        for feature, bits in mapping['features'].items():
            if feature.split('.')[0].lower() not in file.name:
                continue
            if feature not in ('LIOB33.DIFF.DIFF_TERM', 'RIOB33.DIFF.DIFF_TERM'):
                raise RuntimeError('Unsupported termination tile type')
            if feature in content:
                raise RuntimeError('Upstream already defines '+feature)
            if not bits or any(not re.fullmatch(r'!?\d+_\d+', bit) for bit in bits):
                raise RuntimeError('Invalid measured feature bits')
            content += feature+' '+' '.join(bits)+'\n'
        # Replacing a symlink must not change the installed upstream DB.
        temporary = dest.with_suffix('.tmp')
        temporary.write_text(content)
        temporary.replace(dest)
    (overlay.parent/'manifest.json').write_text(json.dumps(dict(
        mapping_sha256=hashlib.sha256(mapping_file.read_bytes()).hexdigest(),
        source_db_sha256=mapping['source_db_sha256'], features=mapping['features']), indent=2)+'\n')
    return overlay
