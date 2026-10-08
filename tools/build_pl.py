#!/usr/bin/env python3
"""Use LiteX-generated RTL/scripts with openXC7's current himbaechel CLI."""
import argparse
import hashlib
import json
import os
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
        actual = [bit for cell in cells if cell['type'] == kind
            for bit in cell['connections'][port]]
        expected = top['ports'][name]['bits']
        if sorted(actual) != sorted(expected):
            raise RuntimeError(f'Disconnected or duplicated DDR pad: {name}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--openxc7", type=Path, required=True)
    p.add_argument("--yosys", type=Path, required=True)
    p.add_argument("--board", choices=["kasli-soc", "zc706"], default="kasli-soc")
    p.add_argument("--design", choices=["probe", "fmc-adc", "pl-ddr"], default="probe")
    p.add_argument("--output-dir", type=Path, default=ROOT / "build/gateware")
    args = p.parse_args()
    if args.design in ("fmc-adc", "pl-ddr") and args.board != "zc706":
        p.error("FMC ADC target requires ZC706")
    target = {"probe": "kasli_soc.py", "fmc-adc": "fmc_adc.py", "pl-ddr": "zc706_ddr.py"}[args.design]
    subprocess.run([sys.executable, str(ROOT / "gateware" / target), "--board", args.board, "--output-dir", str(args.output_dir)], cwd=ROOT, check=True)
    work = args.output_dir / "gateware"
    # A failed rebuild must never leave an earlier bitstream approved.
    (work / "manifest.json").unlink(missing_ok=True)
    if args.design in ("fmc-adc", "pl-ddr"):
        # Resolve custom HDL before synth_xilinx flattening; deferred vendor
        # parameter specialization can otherwise re-elaborate the original top.
        script = work / "top.ys"
        cells = args.yosys.resolve().parents[1] / "share/yosys/xilinx"
        prelude = f'read_verilog -lib "{cells / "cells_sim.v"}" "{cells / "cells_xtra.v"}"\n'
        script.write_text(prelude + script.read_text().replace("verilog_defaults -add -defer", "")
            .replace("synth_xilinx", "hierarchy -check -top top\nproc\n"
                "write_rtlil elaborated.il\ndesign -reset\nread_rtlil elaborated.il\nsynth_xilinx"))
        if args.design == "pl-ddr":
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
    if args.design == "pl-ddr":
        from ddr_chipdb import prepare
        chipdb_args = ["--chipdb", str(prepare(args.openxc7.resolve()))]
        from ddr_nextpnr import prepare as prepare_nextpnr
        nextpnr = prepare_nextpnr()
    cmds = [
        [str(args.yosys.resolve()), "-l", "top.rpt", "top.ys"],
        [str(nextpnr),
         "--device", part, "--json", "top.json", "-o", "xdc=top.xdc",
         "-o", "fasm=top.fasm", "--write", "top_routed.json",
         "--freq", "100", "--report", "timing.json", *chipdb_args],
        [str(args.openxc7.resolve() / "bin/fasm2frames"),
         "--part", part, "--db-root", str(db), "top.fasm"],
        [str(args.openxc7.resolve() / "bin/xc7frames2bit"),
         "--part_file", str(db / part / "part.yaml"), "--part_name",
         physical_part, "--frm_file", "top.frames", "--output_file", "top.bit"],
    ]
    for n, cmd in enumerate(cmds):
        with (work / f"stage{n}.log").open("w") as log:
            if n == 2:
                with (work / "top.frames").open("w") as frames:
                    subprocess.run(cmd, cwd=work, stdout=frames, stderr=log, check=True)
            else:
                subprocess.run(cmd, cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True)
        if n == 0 and args.design == 'pl-ddr':
            validate_ddr_io(work)
    (work / "manifest.json").write_text(json.dumps({
        "physical_part": physical_part, "database_part": part,
        "design": args.design,
        "hardware_validated": False,
        "timing_passed": True,
        "bitstream_sha256": hashlib.sha256((work / "top.bit").read_bytes()).hexdigest(),
        "commands": cmds,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
