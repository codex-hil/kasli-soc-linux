#!/usr/bin/env python3
"""Run ADC snapshot RTL tests with pinned OSS tools."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT/'build/tools/oss-cad-suite/bin'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--soc', action='store_true', help='Also check the synthesized ADC SoC AXI/probe ABI')
parser.add_argument("--output-dir", type=Path, default=ROOT/"build/zc706-adc")
args = parser.parse_args()
BUILD = args.output_dir
OUT = BUILD/"tests"
OUT.mkdir(parents=True, exist_ok=True)
subprocess.run(['python3', ROOT/'tests/adc_driver_test.py'], check=True)
for name, sources in [('capture', ['tests/adc_capture_tb.v', 'gateware/fmc_adc_capture.v']),
                      ('receiver', ['tests/adc_rx_tb.v', 'tests/adc_rx_models.v', 'gateware/fmc_adc_rx.v']),
                      ('dual_capture', ['tests/adc_dual_capture_tb.v', 'gateware/fmc_adc_capture.v'])]:
    subprocess.run([SUITE/'iverilog', '-g2012', '-s', 'tb', '-o', OUT/f'{name}.vvp',
        *[ROOT/s for s in sources]], check=True)
    with (OUT/f'{name}.log').open('w') as log:
        subprocess.run([SUITE/'vvp', OUT/f'{name}.vvp'], stdout=log,
            stderr=subprocess.STDOUT, timeout=30, check=True)
    print((OUT/f'{name}.log').read_text())

if args.soc:
    work = BUILD/'gateware/gateware'
    cells = json.loads((work/'top.json').read_text())['modules']['top']['cells']
    ps = next(c for c in cells.values() if c['type'] == 'PS7')
    gp0_clock = ps['connections']['MAXIGP0ACLK']
    assert any(c['type'] == 'BUFG' and c['connections']['O'] == gp0_clock
               for c in cells.values()), 'GP0 ACLK must use the buffered fabric clock'
    assert any(c['type'].startswith('FD') and c['connections'].get('C') == gp0_clock
               for c in cells.values()), 'GP0 and CSR fabric clocks must be shared'
    print('PASS: hard PS GP0 ACLK shares the fabric BUFG (netlist)')
    subprocess.run([SUITE/'yosys', '-Q', '-T', '-p',
        'read_json top.json; write_verilog -noattr top_sim.v'], cwd=work, check=True,
        stdout=subprocess.DEVNULL)
    csr = json.loads((work.parent/'csr.json').read_text())['csr_registers']
    checks = []
    for name, value in [('adc_control', 0x81), ('adc_ssr', 0x7654321)]+[(f'adc_tap{i}', (3*i+1)%32) for i in range(9)]:
        address = csr[name]['addr']
        checks += [f"write_word(32'h{address:08x},32'h{value:08x});",
                   f"read_word(32'h{address:08x},result);",
                   f'if(result !== {value}) $fatal(1,"{name} readback failed");']
    if 'board_i2c_w' in csr:
        for value in (5, 0, 3, 5):
            address = csr['board_i2c_w']['addr']
            checks += [f"write_word(32'h{address:08x},{value});",
                       f"read_word(32'h{address:08x},result);",
                       f'if(result !== {value}) $fatal(1,"board I2C CSR readback failed");']
        checks += [f"read_word(32'h{csr['board_i2c_r']['addr']:08x},result);",
                   '$display("PASS: board I2C CSR AXI accesses");']
    checks += [f"write_word(32'h{csr['adc_ssr']['addr']:08x},0);",
               f"write_word(32'h{csr['adc_control']['addr']:08x},1);"]
    for name in ('adc_captured', 'adc_errors'):
        checks += [f"read_word(32'h{csr[name]['addr']:08x},result);",
                   f'if(result !== 0) $fatal(1,"{name} reset failed");']
    checks += ['$display("PASS: ADC control/SSR/nine delay CSR readback and reset counters over AXI");']
    if 'adc2_control' in csr:
        for prefix, control, ssr in [('adc', 0x81, 0x1234567), ('adc2', 0x41, 0x7654321)]:
            for name, value in [(prefix+'_control', control), (prefix+'_ssr', ssr)]+[(f'{prefix}_tap{i}', (i*7+control)%32) for i in range(9)]:
                checks += [f"write_word(32'h{csr[name]['addr']:08x},32'h{value:08x});"]
        # Read both banks after writing both: detect aliases/cross-card corruption.
        for prefix, control, ssr in [('adc', 0x81, 0x1234567), ('adc2', 0x41, 0x7654321)]:
            for name, value in [(prefix+'_control', control), (prefix+'_ssr', ssr)]+[(f'{prefix}_tap{i}', (i*7+control)%32) for i in range(9)]:
                checks += [f"read_word(32'h{csr[name]['addr']:08x},result);",
                           f'if(result !== {value}) $fatal(1,"{name} cross-card isolation failed");']
        for prefix, value in [('adc', 0xadc00001), ('adc2', 0xadc00002)]:
            checks += [f"read_word(32'h{csr[prefix+'_card_id']['addr']:08x},result);",
                       f'if(result !== 32\'h{value:08x}) $fatal(1,"{prefix} identity failed");']
        checks += [f"write_word(32'h{csr['adc2_control']['addr']:08x},1);"]
        checks += [f"read_word(32'h{csr['adc_control']['addr']:08x},result);",
                   'if(result !== 129) $fatal(1,"HPC reset changed LPC control");',
                   '$display("PASS: independent LPC/HPC CSR banks, nine taps each, HPC reset isolation over AXI");']

    (OUT/'adc_csr_checks.vh').write_text('\n'.join(checks)+'\n')
    subprocess.run([SUITE/'iverilog', '-g2012', '-DADC_CSR_CHECKS', '-I', OUT,
        '-s', 'tb', '-o', OUT/'axi.vvp',
        ROOT/'tests/axi_csr_tb.v', work/'top_sim.v',
        SUITE.parent/'share/yosys/xilinx/cells_sim.v',
        SUITE.parent/'share/yosys/xilinx/cells_xtra.v'], check=True)
    with (OUT/'axi.log').open('w') as log:
        subprocess.run([SUITE/'vvp', OUT/'axi.vvp'], stdout=log,
            stderr=subprocess.STDOUT, timeout=30, check=True)
    print((OUT/'axi.log').read_text())
    (OUT/'soc-validation.json').write_text(json.dumps({
        'top_json_sha256': hashlib.sha256((work/'top.json').read_bytes()).hexdigest(),
        'csr_json_sha256': hashlib.sha256((work.parent/'csr.json').read_bytes()).hexdigest(),
        'result': 'PASS', 'hardware_validated': False,
    }, indent=2)+'\n')
