#!/usr/bin/env python3
"""Fill two missing Zynq clock activation features using audited Series-7 DBs."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def prepare(original,reference):
    mapping=json.loads((ROOT/'patches/prjxray-zynq-clock-inputs.json').read_text())
    tables={}
    for family,sha in mapping['source_sha256'].items():
        source=reference/family/mapping['file']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:
            raise RuntimeError('Clock source database changed: '+family)
        tables[family]={r[0]:r[1:] for l in source.read_text().splitlines() if (r:=l.split())}
    shared=tables['zynq7'].keys()&tables['artix7'].keys()&tables['spartan7'].keys()
    if len(shared)!=mapping['matching_shared_features'] or not all(
        tables['zynq7'][k]==tables['artix7'][k]==tables['spartan7'][k] for k in shared):
        raise RuntimeError('Series-7 clock mapping does not agree')
    for name,bits in mapping['features'].items():
        if name in tables['zynq7'] or tables['artix7'].get(name)!=bits or tables['spartan7'].get(name)!=bits:
            raise RuntimeError('Clock feature was not audited: '+name)
    if hashlib.sha256((original/mapping['file']).read_bytes()).hexdigest()!=mapping['source_sha256']['zynq7']:
        raise RuntimeError('Overlay clock base differs from audited source')
    out=ROOT/'build/zc706-adc-ddr/clock-db/zynq7'
    out.mkdir(parents=True,exist_ok=True)
    for source in original.iterdir():
        target=out/source.name
        if source.name==mapping['file']:
            if target.is_symlink():target.unlink()
            target.write_text(source.read_text()+''.join(k+' '+' '.join(v)+'\n' for k,v in mapping['features'].items()))
        elif not target.exists():target.symlink_to(source.resolve())
    (out.parent/'manifest.json').write_text(json.dumps(mapping|dict(
        patched_sha256=hashlib.sha256((out/mapping['file']).read_bytes()).hexdigest()),indent=2)+'\n')
    return out
