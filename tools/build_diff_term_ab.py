#!/usr/bin/env python3
"""Build a diagnostic OFF control from the exact routed production FASM.

No rerouting and no Vivado. Require exactly 22 changed non-ECC bits: two per
receiver. This control is for isolated A/B testing, not a release image.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from analyze_diff_term_reference import read_bits

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT/'build/zc706-adc/gateware/gateware'
    out = ROOT/'build/zc706-adc/termination-reference/ab-off'
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((source/'manifest.json').read_text())
    if hashlib.sha256((source/'top.bit').read_bytes()).hexdigest() != manifest['bitstream_sha256']:
        raise RuntimeError('Source bitstream does not match successful manifest')
    fasm = (source/'top.fasm').read_text().splitlines(True)
    removed = [line for line in fasm if line.strip().endswith('.DIFF.DIFF_TERM')]
    if len(removed) != 11:
        raise RuntimeError('Expected eleven termination features')
    (out/'top.fasm').write_text(''.join(line for line in fasm if line not in removed))
    tools = ROOT/'build/tools/openxc7/bin'
    db = ROOT/'build/zc706-adc/termination-db/zynq7'
    part = manifest['database_part']
    with (out/'top.frames').open('w') as frames:
        subprocess.run([tools/'fasm2frames','--part',part,'--db-root',db,out/'top.fasm'], stdout=frames,check=True)
    subprocess.run([tools/'xc7frames2bit','--part_file',db/part/'part.yaml',
        '--part_name',manifest['physical_part'],'--frm_file',out/'top.frames',
        '--output_file',out/'top.bit'],check=True)
    for name, bit in [('on',source/'top.bit'),('off',out/'top.bit')]:
        subprocess.run([tools/'bitread','--part_file',db/part/'part.yaml',
            '-y','-z','-o',out/(name+'.bits'),bit],check=True)
    on,off = read_bits(out/'on.bits'),read_bits(out/'off.bits')
    grid = json.loads((db/'xc7z045/tilegrid.json').read_text())
    mapping = json.loads((ROOT/'patches/prjxray-hr-diff-term.json').read_text())
    expected = set()
    for line in removed:
        tile,_,_ = line.strip().split('.')
        region = grid[tile]['bits']['CLB_IO_CLK']
        for value in mapping['features'][grid[tile]['type']+'.DIFF.DIFF_TERM']:
            frame,bit = map(int,value.split('_'))
            expected.add((int(region['baseaddr'],16)+frame,region['offset']+bit//32,bit%32))
    if off-on or on-off != expected or len(expected) != 22:
        raise RuntimeError('OFF control differs by more than the measured termination bits')
    manifest.update(bitstream_sha256=hashlib.sha256((out/'top.bit').read_bytes()).hexdigest(),
        hardware_validated=False, diagnostic_only=True, fpga_termination=False,
        source_termination=False, on_sha256=hashlib.sha256((source/'top.bit').read_bytes()).hexdigest(),
        changed_non_ecc_bits=22, removed_features=[line.strip() for line in removed])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    shutil.copyfile(source.parent/'csr.json',out/'csr.json')
    print(json.dumps(manifest,indent=2))


if __name__ == '__main__':
    main()
