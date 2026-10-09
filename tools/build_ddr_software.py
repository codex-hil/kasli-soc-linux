#!/usr/bin/env python3
"""Compile unmodified upstream liblitedram training for Linux userspace."""
from pathlib import Path
import argparse
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',type=Path,default=ROOT/'build/zc706-ddr')
parser.add_argument('--cmd-delay',type=int,choices=range(32),help='Diagnostic override of upstream clock/command tap selection')
args=parser.parse_args()
OUT = args.output_dir.resolve()
SW = ROOT/'upstream/litex/litex/soc/software'
INC = OUT/'software/include/hw'
INC.mkdir(parents=True, exist_ok=True)
common=(SW/'include/hw/common.h').read_text()
common,n=re.subn(r'static inline void cdelay\(int i\) \{.*?^\}', 'void cdelay(int i);', common, flags=re.S|re.M)
assert n==1, 'Upstream cdelay changed; re-audit Linux time adapter'
(INC/'common.h').write_text(common)
subprocess.run([ROOT/'build/zc706/buildroot/host/bin/arm-linux-gcc', '-std=gnu11', '-O2', '-static',
    '-D_FILE_OFFSET_BITS=64', '-DMEMTEST_DATA_SIZE=262144', '-ffunction-sections', '-fdata-sections',
    *([] if args.cmd_delay is None else [f'-DSDRAM_PHY_CMD_DELAY={args.cmd_delay}']),
    '-Wl,--gc-sections', '-I'+str(ROOT/'software/pl_ddr/include'),
    '-I'+str(OUT/'software/include'), '-I'+str(OUT/'gateware/include'), '-I'+str(SW),
    ROOT/'software/pl_ddr/main.c', SW/'liblitedram/sdram.c', SW/'liblitedram/accessors.c',
    SW/'libbase/memtest.c', SW/'libbase/format.c', '-o', OUT/'pl-ddr-test'], check=True)
print(OUT/'pl-ddr-test')
