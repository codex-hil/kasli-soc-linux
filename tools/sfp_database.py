#!/usr/bin/env python3
"""Isolated Zynq GTX overlay from pinned openXC7 Kintex-7 GTX definitions.

Zynq's database omits GTX segbits and tile frame ranges. GTX tiles share the
rightmost INT configuration column; the part frame inventory supplies 32
minors, with 0..27 for interconnect and 28..31 for GTX attributes. Frame word
geometry and attributes come from the same 7-series GTX in upstream Kintex.
This overlay is experimental until independently tested on physical ZC706.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(original):
    source = ROOT / "upstream/prjxray-db/kintex7"
    out = ROOT / "build/zc706-sfp/database/zynq7"
    out.mkdir(parents=True, exist_ok=True)
    for item in original.iterdir():
        dst = out / item.name
        if item.name == "xc7z045":
            dst.mkdir(exist_ok=True)
            for f in item.iterdir():
                if f.name != "tilegrid.json" and not (dst/f.name).exists():
                    (dst/f.name).symlink_to(f)
        elif not dst.exists():
            dst.symlink_to(item)
    grid = json.loads((original/"xc7z045/tilegrid.json").read_text())
    kintex = json.loads((source/"xc7k325t/tilegrid.json").read_text())
    part = json.loads((original/"xc7z045ffg900-2/part.json").read_text())
    geometries = {}
    for t in kintex.values():
        if t["type"].startswith("GTX_CHANNEL_") or t["type"] == "GTX_COMMON":
            shape = t["bits"]["CLB_IO_CLK"]
            geometry = {k: shape[k] for k in ("frames", "offset", "words")}
            if geometries.setdefault(t["type"], geometry) != geometry:
                raise RuntimeError("GTX geometry varies across Kintex clock regions")
    # AA18 (TX_DISABLE_N) is documented and exists in RapidWright, but its
    # LIOB33 tile was incorrectly erased to NULL in the Zynq database.
    # Its adjacent LIOI3 already supplies the device-specific frame geometry.
    name = "LIOB33_X0Y23"
    missing = grid[name]
    neighbor = grid["LIOI3_X0Y23"]
    if missing["type"] != "NULL" or missing["sites"]:
        raise RuntimeError("AA18 tile changed; re-audit the missing bank-9 pair")
    donor_grid = json.loads((original/"xc7z030/tilegrid.json").read_text())
    restored = donor_grid[name].copy()
    restored.update(grid_x=missing["grid_x"], grid_y=missing["grid_y"],
                    bits=neighbor["bits"], clock_region=missing["clock_region"])
    restored["pin_functions"] = {"IOB_X0Y23": "IO_L13N_T2_MRCC_9",
                                 "IOB_X0Y24": "IO_L13P_T2_MRCC_9"}
    if restored["sites"] != {"IOB_X0Y23": "IOB33S", "IOB_X0Y24": "IOB33M"}:
        raise RuntimeError("Unexpected donor IOB pair")
    grid[name] = restored
    changes = {}
    for name, t in grid.items():
        if t["type"] not in geometries:
            continue
        region = t["clock_region"]
        adjacent = [x for x in grid.values() if x["type"] == "INT_R"
            and x.get("clock_region") == region and "CLB_IO_CLK" in x["bits"]]
        right = max(adjacent, key=lambda x: x["grid_x"])
        base = int(right["bits"]["CLB_IO_CLK"]["baseaddr"], 16)
        half = "bottom" if base & (1 << 22) else "top"
        row, col = (base >> 17) & 31, (base >> 7) & 1023
        inventory = part["global_clock_regions"][half]["rows"][str(row)][
            "configuration_buses"]["CLB_IO_CLK"]["configuration_columns"][str(col)]
        if inventory["frame_count"] != 32 or base & 127:
            raise RuntimeError("GTX column does not match the device frame inventory")
        shape = {"baseaddr": f"0x{base:08X}", **geometries[t["type"]]}
        if t["bits"] and t["bits"] != {"CLB_IO_CLK": shape}:
            raise RuntimeError("GTX tile already has conflicting frame geometry")
        t["bits"] = {"CLB_IO_CLK": shape}
        changes[name] = shape
    (out/"xc7z045/tilegrid.json").write_text(json.dumps(grid, indent=2)+"\n")
    copied = {}
    for f in source.glob("*gtx*.db"):
        if f.name.endswith(".origin_info.db"):
            continue
        dst = out/f.name
        if dst.is_symlink():
            dst.unlink()
        dst.write_bytes(f.read_bytes())
        copied[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    (out.parent/"manifest.json").write_text(json.dumps({
        "experimental": True, "source_revision": "75825f2e66e16a40a51cf1cfa61afb21f5958afe",
        "source_sha256": copied, "gtx_tiles": changes,
        "restored_aa18_tile": restored,
        "tilegrid_sha256": hashlib.sha256((out/"xc7z045/tilegrid.json").read_bytes()).hexdigest()
    }, indent=2)+"\n")
    return out
