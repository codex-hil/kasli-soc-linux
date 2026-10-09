#!/usr/bin/env python3
"""Use LiteX-generated RTL/scripts with openXC7's current himbaechel CLI."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def validate_ddr_io(work):
    """Reject disconnected bidirectional pads before placement/programming."""
    top = json.loads((work/'top.json').read_text())['modules']['top']
    cells = top['cells'].values()
    if any(cell['type'] in ('$buf', '$_BUF_') for cell in cells):
        raise RuntimeError('Unmapped alias buffer in DDR netlist')
    for name, kind, port in [('ddram_dq', 'IOBUF', 'IO'),
            ('ddram_dqs_p', 'IOBUFDS', 'IO'), ('ddram_dqs_n', 'IOBUFDS', 'IOB')]:
        expected = top['ports'][name]['bits']
        actual = [bit for cell in cells if cell['type'] == kind
            for bit in cell['connections'][port] if bit in expected]
        if sorted(actual) != sorted(expected):
            raise RuntimeError(f'Disconnected or duplicated DDR pad: {name}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--openxc7", type=Path, required=True)
    p.add_argument("--yosys", type=Path, required=True)
    p.add_argument("--board", choices=["kasli-soc", "zc706"], default="kasli-soc")
    p.add_argument("--design", choices=["probe", "fmc-adc", "pl-ddr", "adc-ddr"], default="probe")
    p.add_argument("--output-dir", type=Path, default=ROOT / "build/gateware")
    p.add_argument("--cards", type=int, choices=[1, 2], default=1, help="FMC ADC cards (J5, then J4)")
    p.add_argument("--resume-assembly", action="store_true", help="Reassemble an existing timing-clean ADC DDR route after a DB fix")
    args = p.parse_args()
    if args.cards != 1 and args.design != "fmc-adc":
        p.error("--cards only applies to the FMC ADC target")
    if args.design in ("fmc-adc", "pl-ddr", "adc-ddr") and args.board != "zc706":
        p.error("FMC ADC target requires ZC706")
    target = {"probe": "kasli_soc.py", "fmc-adc": "fmc_adc.py", "pl-ddr": "zc706_ddr.py", "adc-ddr": "zc706_adc_ddr.py"}[args.design]
    target_command = [sys.executable, str(ROOT / "gateware" / target), "--board", args.board, "--output-dir", str(args.output_dir)]
    if args.design == "fmc-adc":
        target_command += ["--cards", str(args.cards)]
    if not args.resume_assembly:
        subprocess.run(target_command, cwd=ROOT, check=True)
    work = args.output_dir / "gateware"
    # A failed rebuild must never leave an earlier bitstream approved.
    (work / "manifest.json").unlink(missing_ok=True)
    if not args.resume_assembly and args.design in ("fmc-adc", "pl-ddr", "adc-ddr"):
        # Resolve custom HDL before synth_xilinx flattening; deferred vendor
        # parameter specialization can otherwise re-elaborate the original top.
        script = work / "top.ys"
        cells = args.yosys.resolve().parents[1] / "share/yosys/xilinx"
        prelude = f'read_verilog -lib "{cells / "cells_sim.v"}" "{cells / "cells_xtra.v"}"\n'
        script.write_text(prelude + script.read_text().replace("verilog_defaults -add -defer", "")
            .replace("synth_xilinx", "hierarchy -check -top top\nproc\n"
                "write_rtlil elaborated.il\ndesign -reset\nread_rtlil elaborated.il\nsynth_xilinx"))
        if args.design in ("pl-ddr", "adc-ddr"):
            # Use stable ABC mapping for the standalone DDR controller.
            script.write_text(script.read_text().replace(" -abc9", ""))
    db = args.openxc7.resolve() / "share/nextpnr/external/prjxray-db/zynq7"
    # FBG/FFG676: 676 identical pin functions, AMD pinout evidence in repo.
    # -1 timing is conservative for the physical -3 device; no GTX in this design.
    part = "xc7z045ffg900-2" if args.board == "zc706" else "xc7z030fbg676-1"
    physical_part = "xc7z045ffg900-2" if args.board == "zc706" else "xc7z030ffg676-3"
    chipdb_args = []
    nextpnr = args.openxc7.resolve() / "bin/nextpnr-xilinx"
    if args.design == "fmc-adc":
        from adc_chipdb import prepare
        chipdb_args = ["--chipdb", str(prepare(args.openxc7.resolve()))]
        from adc_nextpnr import prepare as prepare_nextpnr
        from adc_termination_db import prepare as prepare_termination_db
        nextpnr = prepare_nextpnr()
        db = prepare_termination_db(db)
    if args.design in ("pl-ddr", "adc-ddr"):
        from ddr_chipdb import prepare
        chipdb_args = ["--chipdb", str(prepare(args.openxc7.resolve()))]
        from ddr_nextpnr import prepare as prepare_nextpnr
        nextpnr = prepare_nextpnr()
    if args.design == "adc-ddr":
        from ddr_chipdb import prepare as prepare_ddr
        from adc_chipdb import prepare as prepare_adc
        chipdb_args = ["--chipdb", str(prepare_adc(args.openxc7.resolve(),
            source_binary=prepare_ddr(args.openxc7.resolve()),
            build=ROOT/'build/zc706-adc-ddr/chipdb'))]
        from adc_ddr_nextpnr import prepare as prepare_nextpnr
        from adc_termination_db import prepare as prepare_termination_db
        nextpnr = prepare_nextpnr()
        db = prepare_termination_db(db)
    if args.design == "adc-ddr":
        from adc_ddr_clock_db import prepare as prepare_clock_db
        db = prepare_clock_db(db, args.openxc7.resolve()/"share/nextpnr/external/prjxray-db")
    if args.resume_assembly:
        if args.design != "adc-ddr":
            p.error("Assembly resume is only supported for the combined ADC DDR target")
        latest_input = max((work/name).stat().st_mtime_ns for name in ("top.json", "top.xdc"))
        if any((work/name).stat().st_mtime_ns < latest_input
               for name in ("top.fasm", "timing.json", "stage1.log")):
            raise RuntimeError('Cannot resume a route older than its netlist or constraints')
        timing = json.loads((work/'timing.json').read_text())
        if not timing['fmax'] or any(v['achieved'] < v['constraint'] for v in timing['fmax'].values()):
            raise RuntimeError('Cannot resume a route with failing setup timing')
        log = (work/'stage1.log').read_text()
        hold = re.findall(r'Hold-fix: .*; (\d+) hold violation\(s\) remain\.', log)
        if not hold or hold[-1] != '0' or 'Program finished normally.' not in log:
            raise RuntimeError('Cannot resume without a completed zero-violation hold repair')
        validate_ddr_io(work)
        cells = json.loads((work/'top.json').read_text())['modules']['top']['cells']
        requested = sum(c['type']=='IBUFDS' and c['parameters'].get('DIFF_TERM')=='TRUE' for c in cells.values())
        emitted = sum(line.endswith('.DIFF.DIFF_TERM') for line in (work/'top.fasm').read_text().splitlines())
        if requested != 22 or emitted != 22:
            raise RuntimeError('Resumed route must include all 22 FMC terminations')
    cmds = [
        [str(args.yosys.resolve()), "-l", "top.rpt", "top.ys"],
        [str(nextpnr),
         "--device", part, "--json", "top.json", "-o", "xdc=top.xdc",
         "-o", "fasm=top.fasm", "--write", "top_routed.json",
         "--freq", "100", "--report", "timing.json", *chipdb_args,
         *(["-o", "hold-fix=8", "-o", "hold-buffer-radius=48"] if args.design == "adc-ddr" else [])],
        [str(args.openxc7.resolve() / "bin/fasm2frames"),
         "--part", part, "--db-root", str(db), "top.fasm"],
        [str(args.openxc7.resolve() / "bin/xc7frames2bit"),
         "--part_file", str(db / part / "part.yaml"), "--part_name",
         physical_part, "--frm_file", "top.frames", "--output_file", "top.bit"],
    ]
    for n, cmd in enumerate(cmds):
        if args.resume_assembly and n < 2:
            continue
        with (work / f"stage{n}.log").open("w") as log:
            if n == 2:
                with (work / "top.frames").open("w") as frames:
                    subprocess.run(cmd, cwd=work, stdout=frames, stderr=log, check=True)
            else:
                subprocess.run(cmd, cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True)
        if n == 0 and args.design in ('pl-ddr', 'adc-ddr'):
            validate_ddr_io(work)
        if n == 1 and args.design == 'adc-ddr':
            timing = json.loads((work/'timing.json').read_text())
            if not timing['fmax'] or any(v['achieved'] < v['constraint'] for v in timing['fmax'].values()):
                raise RuntimeError('Combined ADC DDR setup timing must pass and be reported')
            hold = re.findall(r'Hold-fix: .*; (\d+) hold violation\(s\) remain\.',
                              (work/'stage1.log').read_text())
            if not hold or hold[-1] != '0':
                raise RuntimeError('Combined ADC DDR hold timing must pass')
        if n == 1 and args.design in ('fmc-adc', 'adc-ddr'):
            cells = json.loads((work/'top.json').read_text())['modules']['top']['cells']
            requested = sum(c['type'] == 'IBUFDS' and c['parameters'].get('DIFF_TERM') == 'TRUE'
                            for c in cells.values())
            emitted = sum(line.endswith('.DIFF.DIFF_TERM')
                          for line in (work/'top.fasm').read_text().splitlines())
            if requested != 11 * (2 if args.design == "adc-ddr" else args.cards) or emitted != requested:
                raise RuntimeError(f'FPGA termination was not emitted: {emitted}/{requested}')
    (work / "manifest.json").write_text(json.dumps({
        "physical_part": physical_part, "database_part": part,
        "design": args.design,
        "adc_cards": 2 if args.design == "adc-ddr" else args.cards if args.design == "fmc-adc" else None,
        "hardware_validated": False,
        "timing_passed": True,
        "bitstream_sha256": hashlib.sha256((work / "top.bit").read_bytes()).hexdigest(),
        "commands": cmds,
        "route_input_sha256": {name: hashlib.sha256((work/name).read_bytes()).hexdigest()
            for name in ("top.json", "top.fasm", "timing.json")},
        "assembly_resumed": args.resume_assembly,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
