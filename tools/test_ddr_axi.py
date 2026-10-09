#!/usr/bin/env python3
"""Exercise the synthesized DDR target's GP0 CSR path, not a DDR PHY model."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT/'build/tools/oss-cad-suite'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',type=Path,default=ROOT/'build/zc706-ddr')
BUILD = parser.parse_args().output_dir.resolve()
WORK = BUILD/'gateware/gateware'
OUT = BUILD/'tests'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'axi.log').unlink(missing_ok=True)
subprocess.run([SUITE/'bin/yosys', '-Q', '-T', '-p',
    'read_json top.json; write_verilog -noattr top_sim.v'], cwd=WORK,
    stdout=subprocess.DEVNULL, check=True)
text = (ROOT/'tests/axi_csr_tb.v').read_text()
text = text.replace('i<1000', 'i<100').replace('1000 AXI/CSR', '100 AXI/CSR')
text = text.replace('    task write_word',
    '    always @(clk or resetn) begin\n'
    '        force dut.BUFG.O = clk;\n'
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
if 'adc_dma_signature' in csr:
    for name, value in [('adc_card_id',0xadc00001),('adc2_card_id',0xadc00002),
                        ('adc_dma_signature',0x41444452),('adc2_dma_signature',0x41444452)]:
        checks += [f"read_word(32'h{csr[name]['addr']:08x},result);",
                   f'if(result !== {value}) $fatal(1,"ADC DDR CSR {name}: %h",result);']
    for engine in ('adc_dma', 'adc2_dma'):
        # A rejected zero-length request needs no ADC clock or DDR model.
        # Verify that start's added register is visible through a real AXI
        # write acknowledgement followed by a status read.
        checks += [f"write_word(32'h{csr[engine+'_length']['addr']:08x},0);",
                   f"write_word(32'h{csr[engine+'_start']['addr']:08x},1);",
                   f"read_word(32'h{csr[engine+'_status']['addr']:08x},result);",
                   f'if(result !== 18) $fatal(1,"{engine} invalid request: %h",result);']
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
