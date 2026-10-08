#!/usr/bin/env python3
"""Prepare optional Vivado HR termination comparator, never used by make adc-pl.

Route once, then change only DIFF_TERM and write baseline/per-pair/all-on
bitstreams. Outputs are reference data, not images for the laboratory board.
"""
import csv
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
db = ROOT/'build/tools/openxc7/share/nextpnr/external/prjxray-db/zynq7'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--all-pairs', action='store_true', help='Exercise every bonded HR differential pair')
p.add_argument('--output', type=Path, default=ROOT/'build/zc706-adc/termination-reference/golden')
args = p.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
part = 'xc7z020clg400-1'
rows = list(csv.DictReader((db/part/'package_pins.csv').open()))
grid = json.loads((db/'xc7z020/tilegrid.json').read_text())
by_site = {r['site']: r for r in rows}
pairs, banks = [], set()
for row in rows:
    if not row['site'].startswith('IOB_') or (not args.all_pairs and row['bank'] in banks):
        continue
    y = int(row['site'].split('Y')[-1])
    partner = by_site.get(row['site'].split('Y')[0]+'Y'+str(y-1))
    if y % 2 or not partner or partner['tile'] != row['tile']:
        continue
    if grid[row['tile']]['type'] not in ('LIOB33', 'RIOB33'):
        continue
    pairs.append(dict(p=row, n=partner))
    banks.add(row['bank'])
used = {r['pin'] for p in pairs for r in p.values()}
outputs = [r for r in rows if r['site'].startswith('IOB_') and r['pin'] not in used][:1]
if not outputs:
    # Reserve one complete pair for the observable output; test it in a second batch.
    reserved = pairs.pop()
    outputs = [reserved['p']]
else:
    reserved = None
assert len(pairs) >= 3 and len(outputs) == 1
n = len(pairs)
(out/'top.v').write_text('module top(input [%d:0] in_p, in_n, output out);\nwire [%d:0] received;\n' % (n-1, n-1) +
    ''.join('IBUFDS #(.IOSTANDARD("LVDS_25"), .DIFF_TERM("FALSE")) receiver%d '
            '(.I(in_p[%d]), .IB(in_n[%d]), .O(received[%d]));\n' % (i,i,i,i) for i in range(n))+
    'assign out = ^received;\nendmodule\n')
constraints = []
for i,pair in enumerate(pairs):
    for polarity in ('p','n'):
        constraints.append('set_property -dict {PACKAGE_PIN %s IOSTANDARD LVDS_25} '
                           '[get_ports {in_%s[%d]}]' % (pair[polarity]['pin'], polarity, i))
constraints.append('set_property -dict {PACKAGE_PIN %s IOSTANDARD LVCMOS25} '
                   '[get_ports out]' % outputs[0]['pin'])
tcl = '''create_project -in_memory -part %s
read_verilog top.v
synth_design -top top
%s
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 2.5 [current_design]
set_property BITSTREAM.GENERAL.COMPRESS FALSE [current_design]
opt_design
place_design
route_design
report_io -file baseline-io.txt
write_checkpoint -force routed.dcp
proc emit {name enabled} {
    for {set i 0} {$i < %d} {incr i} {
        set val [expr {[lsearch -exact $enabled $i] >= 0 ? "TRUE" : "FALSE"}]
        set_property DIFF_TERM $val [get_ports [format {in_p[%%d]} $i]]
    }
    report_io -file $name-io.txt
    write_bitstream -force $name.bit
}
emit off {}
''' % (part, '\n'.join(constraints), n)
tcl += ''.join('emit pair%d {%d}\n' % (i,i) for i in range(n))
tcl += 'emit all {%s}\nemit off-repeat {}\n' % ' '.join(map(str,range(n)))
(out/'reference.tcl').write_text(tcl)
(out/'pins.json').write_text(json.dumps(dict(part=part, pairs=pairs, outputs=outputs,
    reserved_pair=reserved, all_bonded_pairs=args.all_pairs), indent=2)+'\n')
print(out)
