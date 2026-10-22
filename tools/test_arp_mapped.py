#!/usr/bin/env python3
"""Compare actual ARP self-test RTL with Yosys-mapped SRL/no-SRL netlists."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'gateware'))
from migen.fhdl import verilog
from zc706_arp import ARPSelfTest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--yosys',default='/usr/bin/yosys')
    p.add_argument('--cells-sim',default='/usr/share/yosys/xilinx/cells_sim.v')
    a = p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    out = a.output.resolve()
    dut = ARPSelfTest()
    signals = {dut.run.storage:'run', dut.gap.storage:'gap'}
    for name in ('busy','sent','received','errors','last_ip','last_mac_lo','last_mac_hi'):
        signals[getattr(dut,name).status] = name
    for signal,name in signals.items():signal.name_override = name
    (out/'rtl.v').write_text(str(verilog.convert(dut,ios=set(signals),name='arp_test')))
    (out/'tb.v').write_text('''module tb;
reg sys_clk=0, sys_rst=1, run=0;
reg [1:0] gap=0;
wire busy;wire [31:0] sent,received,errors,last_ip,last_mac_lo;
wire [15:0] last_mac_hi;
arp_test dut(.sys_clk(sys_clk),.sys_rst(sys_rst),.run(run),.gap(gap),
 .busy(busy),.sent(sent),.received(received),.errors(errors),
 .last_ip(last_ip),.last_mac_lo(last_mac_lo),.last_mac_hi(last_mac_hi));
always #5 sys_clk=~sys_clk;
integer n,g;
initial begin
 repeat(5) @(negedge sys_clk);sys_rst=0;
 for(g=0;g<3;g=g+1) begin
  gap=(g==2)?3:g;run=1;
  repeat(6000) @(negedge sys_clk);run=0;
  repeat(300) @(negedge sys_clk);
  $display("gap=%d sent=%d received=%d errors=%d ip=%h mac=%h%h",gap,sent,received,errors,last_ip,last_mac_hi,last_mac_lo);
  if(busy!==0 || sent<20 || received!==sent || errors!==0 || last_ip!==32'hc0a8026b || {last_mac_hi,last_mac_lo}!==48'h6c2b59f476e8)
   $fatal(1,"ARP decoded fields/count mismatch");
 end
 $display("PASS");$finish;
end
endmodule
''')
    baseline = subprocess.run([sys.executable,str(ROOT/'tools/test_arp_selftest.py')],check=True,timeout=60,capture_output=True,text=True)
    (out/'rtl-migen.log').write_text(baseline.stdout+baseline.stderr)
    if 'PASS:' not in baseline.stdout:
        raise RuntimeError('Missing Migen baseline completion marker')
    result = {'yosys_version':subprocess.check_output([a.yosys,'-V'],text=True).strip(),'hardware_access':False,'rtl_baseline':'Migen simulation PASS, same module/input cases','cases':{}}
    def run_logged(command, name, check=True):
        with (out/name).open('w') as log:
            r = subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=check)
        return r.returncode
    for mode in ('srl','no-srl'):
        source = 'rtl.v'
        entry = {}
        if mode != 'rtl':
            source = mode+'.v'
            script = f'read_verilog rtl.v; synth_xilinx -flatten -abc9 -arch xc7 -top arp_test {"-nosrl" if mode=="no-srl" else ""}; write_json {mode}.json; write_verilog -noattr {source}'
            run_logged([a.yosys,'-p',script],mode+'-yosys.log')
            cells = json.loads((out/(mode+'.json')).read_text())['modules']['arp_test']['cells']
            entry['srl_count'] = sum(c['type']=='SRL16E' for c in cells.values())
            if entry['srl_count'] != (8 if mode=='srl' else 0):
                raise RuntimeError('Mapped simulation changed the SRL topology')
        run_logged([str(ROOT/'build/tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',mode+'.vvp','tb.v',source,
            a.cells_sim],mode+'-compile.log')
        try:
            code = run_logged([str(ROOT/'build/tools/oss-cad-suite/bin/vvp'),mode+'.vvp'],mode+'-simulation.log',check=False)
        except subprocess.TimeoutExpired:
            code = 124
        transcript = (out/(mode+'-simulation.log')).read_text()
        entry.update(result='PASS' if code==0 and 'PASS' in transcript else 'INCONCLUSIVE' if code==0 else 'TIMEOUT' if code==124 else 'FAIL',returncode=code,
            transcript=(out/(mode+'-simulation.log')).read_text(),source_sha256=hashlib.sha256((out/source).read_bytes()).hexdigest())
        result['cases'][mode] = entry
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':main()
