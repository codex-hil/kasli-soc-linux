#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build isolated SRL16E timing experiment; never replace qualified tools."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from sfp_nextpnr import prepare as prepare_base
from srl_timing_model import model, header
ROOT = Path(__file__).resolve().parents[1]


def prepare():
    base = prepare_base()
    out = ROOT/'build/zc706-srl-timing/nextpnr'
    out.mkdir(parents=True, exist_ok=True)
    binary = out/'nextpnr-himbaechel-xilinx'
    patch = ROOT/'patches/nextpnr-srl-timing.inc'
    values = model(ROOT/'upstream/prjxray-db/zynq7/timings/slicem.sdf')
    identity = {'base_binary_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
        'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
        'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'model': values}
    marker = out/'manifest.json'
    if marker.exists() and binary.exists():
        cached = json.loads(marker.read_text())
        if all(cached.get(k) == v for k,v in identity.items()) and cached.get('binary_sha256') == hashlib.sha256(binary.read_bytes()).hexdigest():
            return binary
    source = out/'source/himbaechel/uarch/xilinx'
    shutil.copytree(base.parent/'source/himbaechel/uarch/xilinx', source, dirs_exist_ok=True)
    h = source/'xilinx.h'
    declarations = '''    bool getCellDelay(const CellInfo *, IdString, IdString, DelayQuad &) const override;
    TimingPortClass getPortTimingClass(const CellInfo *, IdString, int &) const override;
    TimingClockingInfo getPortClockingInfo(const CellInfo *, IdString, int) const override;
'''
    text = h.read_text()
    assert text.count('    ~XilinxImpl();') == 1
    h.write_text(text.replace('    ~XilinxImpl();', declarations+'    ~XilinxImpl();'))
    cc = source/'xilinx.cc'
    text = cc.read_text()
    assert text.count('NEXTPNR_NAMESPACE_END') == 1
    cc.write_text(text.replace('NEXTPNR_NAMESPACE_END', patch.read_text()+'\nNEXTPNR_NAMESPACE_END'))
    (source/'srl_timing_values.h').write_text(header(values))
    work = ROOT/'build/zc706-ddr/nextpnr-build/himbaechel/uarch/xilinx'
    objects = work/'CMakeFiles/nextpnr-himbaechel-xilinx.dir'
    flags = {}
    for line in (objects/'flags.make').read_text().splitlines():
        if line.startswith(('CXX_DEFINES =', 'CXX_INCLUDES =', 'CXX_FLAGS =')):
            key,value = line.split('=',1)
            flags[key.strip()] = shlex.split(value.replace('-flto=auto','-flto=2'))
    subprocess.run(['/usr/bin/c++', *flags['CXX_DEFINES'], *flags['CXX_INCLUDES'], *flags['CXX_FLAGS'],
        '-c',str(cc),'-o',str(out/'xilinx.cc.o')],check=True)
    command = []; output = False
    replacements = {'xilinx.cc.o':out/'xilinx.cc.o',
        'hold_fix.cc.o': ROOT/'build/zc706-adc-ddr/nextpnr-hold/hold_fix.cc.o',
        'pack_io.cc.o':base.parent/'pack_io.cc.o', 'fasm.cc.o':base.parent/'fasm.cc.o'}
    for token in shlex.split((objects/'link.txt').read_text()):
        if output: command.append(str(binary)); output = False
        elif token == '-o': command.append(token); output = True
        elif token.startswith('-Wl,--dependency-file='): command.append('-Wl,--dependency-file='+str(out/'link.d'))
        elif token == '-flto=auto': command.append('-flto=2')
        elif token.endswith(('.o','.a')):
            path = work/token
            command.append(str(replacements.get(path.name,path).resolve()))
        else: command.append(token)
    subprocess.run(command,cwd=out,check=True)
    marker.write_text(json.dumps(identity | {'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()},indent=2)+'\n')
    return binary


if __name__ == '__main__':
    print(prepare())
