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
parser.add_argument('--trace-dfi',action='store_true',help='Instrument an isolated liblitedram copy with bounded byte-four raw DFI logs')
parser.add_argument('--dqs-sweep',action='store_true',help='Build bounded byte-four DQS/read sweep diagnostic')
args=parser.parse_args()
OUT = args.output_dir.resolve()
SW = ROOT/'upstream/litex/litex/soc/software'
INC = OUT/'software/include/hw'
INC.mkdir(parents=True, exist_ok=True)
common=(SW/'include/hw/common.h').read_text()
common,n=re.subn(r'static inline void cdelay\(int i\) \{.*?^\}', 'void cdelay(int i);', common, flags=re.S|re.M)
assert n==1, 'Upstream cdelay changed; re-audit Linux time adapter'
(INC/'common.h').write_text(common)
sdram_source = SW/'liblitedram/sdram.c'
if args.trace_dfi:
    text = sdram_source.read_text()
    declaration = 'static unsigned int sdram_write_read_check_test_pattern(int module, unsigned int seed, int dq_line) {\n'
    assert text.count(declaration) == 1, 'Upstream pattern function changed'
    text = text.replace(declaration, declaration +
        '\tstatic unsigned trace_calls, trace_rows;\n\tif (module == 4) trace_calls++;\n', 1)
    anchor = '\t\tcsr_rd_buf_uint8(sdram_dfii_pix_rddata_addr(p), tst, DFII_PIX_DATA_BYTES);\n'
    assert text.count(anchor) == 1, 'Upstream DFI read changed'
    trace = r"""
        if (module == 4 && trace_rows < 256 &&
            (trace_calls <= 8 || trace_calls % 128 == 0)) {
            printf("DFI_TRACE call=%u module=%d seed=%u phase=%d select=%08x expected=",
                trace_calls, module, seed, p, ddrphy_dly_sel_read());
            for (int trace_i=0; trace_i<DFII_PIX_DATA_BYTES; trace_i++)
                printf("%02x", prs[p][trace_i]);
            printf(" actual=");
            for (int trace_i=0; trace_i<DFII_PIX_DATA_BYTES; trace_i++)
                printf("%02x", tst[trace_i]);
            printf("\n");
            trace_rows++;
        }
"""
    text = text.replace(anchor, anchor + trace, 1)
    sdram_source = OUT/'software/sdram-dfi-trace.c'
    sdram_source.write_text(text)
if args.dqs_sweep:
    text = sdram_source.read_text()
    text += '\n' + (ROOT/'software/pl_ddr/dqs_sweep.c.inc').read_text()
    sdram_source = OUT/'software/sdram-dqs-sweep.c'
    sdram_source.write_text(text)
subprocess.run([ROOT/'build/zc706/buildroot/host/bin/arm-linux-gcc', '-std=gnu11', '-O2', '-static',
    '-D_FILE_OFFSET_BITS=64', '-DMEMTEST_DATA_SIZE=262144', '-ffunction-sections', '-fdata-sections',
    *([] if args.cmd_delay is None else [f'-DSDRAM_PHY_CMD_DELAY={args.cmd_delay}']),
    *(['-DSDRAM_LAB_DQS_SWEEP'] if args.dqs_sweep else []),
    '-Wl,--gc-sections', '-I'+str(ROOT/'software/pl_ddr/include'),
    '-I'+str(OUT/'software/include'), '-I'+str(OUT/'gateware/include'), '-I'+str(SW),
    ROOT/'software/pl_ddr/main.c', sdram_source, SW/'liblitedram/accessors.c',
    SW/'libbase/memtest.c', SW/'libbase/format.c', '-o', OUT/'pl-ddr-test'], check=True)
print(OUT/'pl-ddr-test')
