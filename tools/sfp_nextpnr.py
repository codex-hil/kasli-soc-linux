#!/usr/bin/env python3
"""Isolated GTX reference-selector/fabric-clock routing fix; qualified ADC/DDR tools stay intact."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from adc_ddr_nextpnr import prepare as prepare_base
ROOT = Path(__file__).resolve().parents[1]


def prepare():
    base = prepare_base()
    out = ROOT/'build/zc706-sfp/nextpnr'
    out.mkdir(parents=True, exist_ok=True)
    binary = out/'nextpnr-himbaechel-xilinx'
    patch = ROOT/'patches/nextpnr-gtx-fabric-refclk.patch'
    identity = dict(base_binary_sha256=hashlib.sha256(base.read_bytes()).hexdigest(),
                    patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest())
    marker = out/'manifest.json'
    if marker.exists() and binary.exists():
        cached = json.loads(marker.read_text())
        if all(cached.get(k) == v for k,v in identity.items()) and cached.get('binary_sha256') == hashlib.sha256(binary.read_bytes()).hexdigest():
            return binary
    source = out/'source/himbaechel/uarch/xilinx'
    shutil.copytree(base.parent/'source/himbaechel/uarch/xilinx', source, dirs_exist_ok=True)
    subprocess.run(['patch', '--batch', '-p1', '-i', str(patch.resolve())], cwd=out/'source', check=True)
    work = ROOT/'build/zc706-ddr/nextpnr-build/himbaechel/uarch/xilinx'
    objects = work/'CMakeFiles/nextpnr-himbaechel-xilinx.dir'
    flags = {}
    for line in (objects/'flags.make').read_text().splitlines():
        if line.startswith(('CXX_DEFINES =', 'CXX_INCLUDES =', 'CXX_FLAGS =')):
            key, value = line.split('=', 1)
            flags[key.strip()] = shlex.split(value.replace('-flto=auto', '-flto=2'))
    for name in ('pack_io.cc', 'fasm.cc'):
        subprocess.run(['/usr/bin/c++', *flags['CXX_DEFINES'], *flags['CXX_INCLUDES'], *flags['CXX_FLAGS'],
                        '-c', str(source/name), '-o', str(out/(name+'.o'))], check=True)
    command = []; output = False
    for token in shlex.split((objects/'link.txt').read_text()):
        if output: command.append(str(binary)); output = False
        elif token == '-o': command.append(token); output = True
        elif token.startswith('-Wl,--dependency-file='): command.append('-Wl,--dependency-file='+str(out/'link.d'))
        elif token == '-flto=auto': command.append('-flto=2')
        elif token.endswith(('.o', '.a')):
            path = work/token
            if path.name in ('hold_fix.cc.o', 'xilinx.cc.o'): path = base.parent/path.name
            if path.name in ('pack_io.cc.o', 'fasm.cc.o'): path = out/path.name
            command.append(str(path.resolve()))
        else: command.append(token)
    subprocess.run(command, cwd=out, check=True)
    marker.write_text(json.dumps(identity|dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()), indent=2)+'\n')
    return binary


if __name__ == '__main__': print(prepare())
