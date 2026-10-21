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
    if "main_srl_inferred_depth4" in module["netnames"]:
        return check_inferred(module)
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


def check_inferred(module):
    cells = module["cells"]
    srls = {n: c for n, c in cells.items() if c["type"] == "SRL16E"}
    assert len(srls) == 32, "Expected 16 explicit and 16 inferred SRLs"
    taps = Counter()
    drivers = {}
    for name, cell in cells.items():
        for bit in cell["connections"].get("Q", []):
            drivers.setdefault(bit, []).append((name, cell))
    for name, cell in srls.items():
        assert cell["connections"]["CE"] == ["1"]
        assert int(cell["parameters"]["INIT"], 2) == 0
        tap = sum(int(cell["connections"]["A"+str(i)][0]) << i for i in range(4))
        taps[("explicit" if name.startswith("SRL16E") else "inferred", tap)] += 1
    # The shared prefix becomes two four-cycle SRLs for the eight-cycle path.
    assert taps == Counter({("explicit", 2): 8, ("explicit", 6): 8,
                            ("inferred", 3): 16}), taps
    references = {}
    paths = {}
    for depth in (4, 8):
        reference = module["netnames"]["main_srl_reference_depth"+str(depth)]["bits"]
        assert len(reference) == depth * 8
        types = []
        for bit in reference:
            ds = drivers.get(bit, [])
            assert len(ds) == 1 and ds[0][1]["type"] in ("FDRE", "FDSE"), ds
            types.append(ds[0][1]["type"])
        references[str(depth)] = dict(Counter(types))
        output = module["netnames"]["main_srl_inferred_depth"+str(depth)]["bits"][-8:]
        lengths = []
        for bit in output:
            length = 0
            seen = set()
            while len(drivers.get(bit, [])) == 1 and drivers[bit][0][1]["type"] == "SRL16E":
                assert bit not in seen, "SRL cycle"
                seen.add(bit)
                cell = drivers[bit][0][1]
                length += 1 + sum(int(cell["connections"]["A"+str(i)][0]) << i for i in range(4))
                bit = cell["connections"]["D"][0]
            assert length == depth, (depth, length)
            lengths.append(length)
        paths[str(depth)] = lengths
    return {"result": "PASS", "abi": 3, "srl_count": 32,
            "inferred_lane_delays": paths, "reference_types": references,
            "tap_inventory": {str(k): v for k, v in taps.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.netlist), indent=2) + "\n")


if __name__ == "__main__":
    main()
