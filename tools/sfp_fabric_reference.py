#!/usr/bin/env python3
"""Prepare an optional XC7Z030 GTX clock model; never program its bitstream."""
import argparse
from pathlib import Path
import re
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=Path("build/zc706-sfp/gateware/gateware"))
    parser.add_argument("--output", type=Path,
                        default=Path("build/zc706-sfp/fabric-refclk-fuzz"))
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if source == output or source in output.parents:
        parser.error("Model output must be separate from the hardware source")
    original = (source / "top.v").read_text()
    if not re.search(r"wire\s+ps7_clk;", original):
        parser.error("Expected generated PS7 FCLK net ps7_clk")
    for mode in ("fabric", "local"):
        dest = output / mode
        dest.mkdir(parents=True, exist_ok=True)
        verilog = original
        ports = {
            "CPLL_FBDIV_45": "3'd5",
            "CPLLREFCLKSEL": "3'd7" if mode == "fabric" else "3'd2",
            "GTNORTHREFCLK1": "1'd0",
            "GTREFCLK1": "pma_k7_gtx_basex_refclk",
            "GTGREFCLK": "ps7_clk" if mode == "fabric" else "1'd0",
        }
        for port, value in ports.items():
            verilog, count = re.subn(
                r"(\." + port + r"\s*\()[^)]*(\))",
                lambda match: match[1] + value + match[2], verilog)
            if count != 1:
                parser.error(f"Expected exactly one {port}, found {count}")
        (dest / "top.v").write_text(verilog)
        for init in source.glob("*.init"):
            shutil.copyfile(init, dest / init.name)
        lines = []
        for line in (source / "top.xdc").read_text().splitlines():
            if line.startswith("set_property LOC "):
                continue  # ZC706 pad locations do not apply to this model.
            if line.startswith("create_clock "):
                line = line.replace("get_ports ", "get_nets ")
            lines.append(line)
        lines.extend([
            "set_property LOC GTXE2_CHANNEL_X0Y0 "
            "[get_cells -hierarchical -filter {REF_NAME == GTXE2_CHANNEL}]",
            "set_property LOC IBUFDS_GTE2_X0Y1 "
            "[get_cells -hierarchical -filter {REF_NAME == IBUFDS_GTE2}]",
        ])
        (dest / "top.xdc").write_text("\n".join(lines) + "\n")
    print(f"Prepared model-only variants in {output}; never program on ZC706")


if __name__ == "__main__":
    main()
