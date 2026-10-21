#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded Linux SRL diagnostic; call only inside the shared board lease."""
import argparse
import json
import time
from pathlib import Path
from sfp_probe import Registers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csr-json", required=True)
    parser.add_argument("--device", default="/dev/uio0")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"result": "FAIL", "samples": [], "scope": "Yosys inferred low16 versus explicit SRL+FF high16, byte delays4/8, FF references"}
    regs = None
    try:
        regs = Registers(args.csr_json, args.device)
        if regs.read("srl_signature") != 0x53524c33:
            raise RuntimeError("SRL diagnostic signature mismatch")
        for _ in range(10):
            sample = {name: regs.read("srl_" + name)
                      for name in ("cycles", "errors", "ready", "polarity")}
            sample["inferred_errors"] = sample["errors"] & 0xffff
            sample["explicit_errors"] = sample["errors"] >> 16
            result["samples"].append(sample)
            if not sample["ready"] or sample["errors"] or sample["polarity"]:
                raise RuntimeError("SRL versus flip-flop mismatch or not ready")
            time.sleep(0.1)
        cycles = [sample["cycles"] for sample in result["samples"]]
        if any(not 1_000_000 < ((b-a) & 0xffffffff) < 100_000_000
               for a, b in zip(cycles, cycles[1:])):
            raise RuntimeError("Diagnostic clock is stalled or unexpected")
        result["result"] = "PASS"
    except Exception as error:
        result["error"] = str(error)
    finally:
        if regs is not None:
            regs.mem.close()
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    if result["result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
