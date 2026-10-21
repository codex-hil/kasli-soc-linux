#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Admit the CE comparison netlist; never accesses hardware."""
import argparse
from collections import Counter
import json
from pathlib import Path


def check(path):
    module = json.loads(path.read_text())["modules"]["top"]
    cells = module["cells"]
    srls = {name: cell for name, cell in cells.items() if cell["type"] == "SRL16E"}
    assert len(srls) == 32, "Expected exactly 32 explicit SRL16E"
    modes = Counter()
    for cell in srls.values():
        ce = cell["connections"]["CE"]
        mode = "constant" if ce == ["1"] else "variable"
        assert mode == "constant" or isinstance(ce[0], int), "Unexpected CE tie"
        assert int(cell["parameters"]["INIT"], 2) == 0, "Expected zero INIT"
        address = sum(int(cell["connections"]["A"+str(i)][0]) << i for i in range(4))
        modes[(mode, address)] += 1
    assert modes == Counter({(mode, tap): 1 for mode in ("constant", "variable") for tap in range(16)}), modes
    references = {}
    for name in ("main_srl_reference_gap", "main_srl_reference_always"):
        bits = module["netnames"][name]["bits"]
        assert len(bits) == 16
        types = []
        for bit in bits:
            drivers = [cell["type"] for cell in cells.values()
                       if bit in cell["connections"].get("Q", [])]
            assert len(drivers) == 1 and drivers[0] in ("FDRE", "FDSE"), drivers
            types += drivers
        references[name] = dict(Counter(types))
    return {"result": "PASS", "srl_count": len(srls),
            "constant_ce_taps": list(range(16)), "variable_ce_taps": list(range(16)),
            "reference_types": references}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.netlist), indent=2) + "\n")


if __name__ == "__main__":
    main()
