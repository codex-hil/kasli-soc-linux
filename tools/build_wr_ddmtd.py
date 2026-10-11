#!/usr/bin/env python3
"""Translate unmodified pinned WR DDMTD VHDL to Verilog with GHDL (no Vivado)."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    common = ROOT/'upstream/general-cores-wr/modules/common'
    timing = ROOT/'upstream/wr-cores-afcz-v5/modules/timing'
    sources = [common/(n+'.vhd') for n in ('gencores_pkg', 'gc_sync', 'gc_edge_detect',
        'gc_sync_ffs', 'gc_sync_register', 'gc_pulse_synchronizer2', 'gc_extend_pulse')]
    sources += [timing/(n+'.vhd') for n in ('dmtd_sampler', 'dmtd_with_deglitcher')]
    work = ROOT/'build/wr-ddmtd'
    work.mkdir(parents=True, exist_ok=True)
    output = work/'tagger.v'
    identity = dict(sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        ghdl=subprocess.check_output(['ghdl','--version'], text=True), tag_bits=32,
        options=['--std=08', '-frelaxed-rules', '--no-formal'], license='LGPL-2.1-or-later WR / Solderpad-2.0 general-cores')
    marker = work/'manifest.json'
    if marker.exists() and output.exists():
        cached = json.loads(marker.read_text())
        if all(cached.get(k)==v for k,v in identity.items()) and cached.get('verilog_sha256')==hashlib.sha256(output.read_bytes()).hexdigest():
            return output
    flags = ['--std=08', '-frelaxed-rules', '--workdir='+str(work)]
    with (work/'ghdl.log').open('w') as log:
        subprocess.run(['ghdl','-a',*flags,*map(str,sources)], stdout=log, stderr=log, check=True)
        with output.open('w') as rtl:
            rtl.write('// Derived from CERN White Rabbit LGPL-2.1-or-later and\n'
                '// CERN general-cores Solderpad-2.0 VHDL. See build manifest for exact sources.\n')
            subprocess.run(['ghdl','--synth',*flags,'--no-formal','--out=verilog','-gg_counter_bits=32',
                'dmtd_with_deglitcher'], stdout=rtl, stderr=log, check=True)
    marker.write_text(json.dumps(identity|dict(verilog_sha256=hashlib.sha256(output.read_bytes()).hexdigest()),indent=2)+'\n')
    return output


if __name__ == '__main__':
    print(prepare())
