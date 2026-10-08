#!/usr/bin/env python3
"""Exercise the synthesized DDR target's GP0 CSR path, not a DDR PHY model."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT/'build/tools/oss-cad-suite'
WORK = ROOT/'build/zc706-ddr/gateware/gateware'
OUT = ROOT/'build/zc706-ddr/tests'
OUT.mkdir(exist_ok=True)
(OUT/'axi.log').unlink(missing_ok=True)
subprocess.run([SUITE/'bin/yosys', '-Q', '-T', '-p',
    'read_json top.json; write_verilog -noattr top_sim.v'], cwd=WORK,
    stdout=subprocess.DEVNULL, check=True)
text = (ROOT/'tests/axi_csr_tb.v').read_text()
text = text.replace('i<1000', 'i<100').replace('1000 AXI/CSR', '100 AXI/CSR')
text = text.replace('    task write_word',
    '    always @(clk or resetn) begin\n'
    '        force dut.sys_clk = clk;\n'
    '        force dut.MMCME2_ADV.LOCKED = resetn[0];\n'
    '    end\n'
    '    task write_word')
text = text.replace('        force dut.PS7.FCLKRESETN = resetn;',
    '        force dut.PS7.MAXIGP1AWVALID = 0;\n'
    '        force dut.PS7.MAXIGP1WVALID = 0;\n'
    '        force dut.PS7.MAXIGP1ARVALID = 0;\n'
    '        force dut.PS7.MAXIGP1BREADY = 0;\n'
    '        force dut.PS7.MAXIGP1RREADY = 0;\n'
    '        force dut.PS7.FCLKRESETN = resetn;')
csr = json.loads((WORK.parent/'csr.json').read_text())['csr_registers']
checks = []
for name, value in [('ddr_status_signature', 0x504c4444),
        ('ddrphy_rdphase', 2), ('ddrphy_wrphase', 1)]:
    if name.endswith('phase'):
        checks.append(f"write_word(32'h{csr[name]['addr']:08x},32'h{value:08x});")
    checks += [f"read_word(32'h{csr[name]['addr']:08x},result);",
        f'if(result !== {value}) $fatal(1,"DDR CSR {name}: %h",result);']
checks.append('$display("PASS: DDR target GP0 signature and PHY CSR read/write (simulation)");')
text = text.replace('        $finish;', '\n'.join(checks)+'\n        $finish;')
(OUT/'axi_ddr_tb.v').write_text(text)
subprocess.run([SUITE/'bin/iverilog', '-g2012', '-s', 'tb', '-o', OUT/'axi.vvp',
    OUT/'axi_ddr_tb.v', WORK/'top_sim.v', SUITE/'share/yosys/xilinx/cells_sim.v',
    SUITE/'share/yosys/xilinx/cells_xtra.v'], check=True)
with (OUT/'axi.log').open('w') as log:
    subprocess.run([SUITE/'bin/vvp', OUT/'axi.vvp'], stdout=log,
        stderr=subprocess.STDOUT, check=True, timeout=180)
print((OUT/'axi.log').read_text())
