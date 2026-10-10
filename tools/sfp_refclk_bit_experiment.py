#!/usr/bin/env python3
"""Assemble a ZC706-only fabric-reference bit experiment from a routed OSS build."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--openxc7', required=True, type=Path)
    p.add_argument('--bits', default='9,10,54', help='Channel-relative bits in minor 31')
    a = p.parse_args()
    bits = [int(x) for x in a.bits.split(',')]
    if not bits or len(set(bits)) != len(bits) or not set(bits) <= {9, 10, 54}:
        p.error('Only the three measured candidate bits 9,10,54 are permitted')
    source = a.source.resolve()
    output = a.output.resolve()
    if source == output or source in output.parents or output in source.parents:
        p.error('Experiment output must be separate from the source tree')
    gateware = source/'gateware'
    manifest = json.loads((gateware/'manifest.json').read_text())
    if (manifest.get('design'), manifest.get('sfp_refclk'), manifest.get('physical_part')) != (
            'sfp', 'fclk', 'xc7z045ffg900-2') or not manifest.get('timing_passed'):
        p.error('Requires a timing-checked ZC706 OSS fabric-reference build')
    original_digest = hashlib.sha256((gateware/'top.bit').read_bytes()).hexdigest()
    if manifest['bitstream_sha256'] != original_digest:
        p.error('Source bitstream does not match its manifest')
    grid = json.loads((a.openxc7.resolve().parents[1]/'zc706-sfp/database/zynq7/xc7z045/tilegrid.json').read_text())
    geometry = grid['GTX_CHANNEL_2_X249Y139']['bits']['CLB_IO_CLK']
    if geometry['offset'] != 57 or geometry['words'] != 22:
        p.error('Unexpected SFP GTX channel geometry')
    frame = int(geometry['baseaddr'], 16) + 31
    dest = output/'gateware'
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source/'csr.json', output/'csr.json')
    lines = []
    found = False
    changes = []
    for line in (gateware/'top.frames').read_text().splitlines():
        address, data = line.split()
        words = [int(x,16) for x in data.split(',')]
        if int(address,16) == frame:
            found = True
            for bit in bits:
                word = geometry['offset'] + bit//32
                mask = 1 << (bit % 32)
                if words[word] & mask:
                    p.error(f'Candidate bit {bit} is already set in source')
                words[word] |= mask
                changes.append({'frame':hex(frame), 'word':word, 'bit':bit % 32})
        lines.append(address+' '+','.join(f'0x{x:08X}' for x in words))
    if not found:
        p.error('SFP GTX configuration frame was absent')
    frames = dest/'top.frames'
    frames.write_text('\n'.join(lines)+'\n')
    tool = a.openxc7.resolve()
    subprocess.run([str(tool/'bin/xc7frames2bit'), '--part_file',
        str(tool/'share/nextpnr/external/prjxray-db/zynq7/xc7z045ffg900-2/part.yaml'),
        '--part_name','xc7z045ffg900-2','--frm_file',str(frames),
        '--output_file',str(dest/'top.bit')],check=True)
    manifest.update(hardware_validated=False,
        bitstream_sha256=hashlib.sha256((dest/'top.bit').read_bytes()).hexdigest(),
        configuration_experiment={'source_bitstream_sha256':original_digest,
            'model_evidence':'evidence/zc706/sfp-20261010/vivado-fabric-refclk-model.json',
            'added_bits':changes,'routing_unchanged':True,'normal_build':False})
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest['configuration_experiment'],indent=2))


if __name__ == '__main__':
    main()
