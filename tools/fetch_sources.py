#!/usr/bin/env python3
"""Fetch immutable source revisions without resetting existing checkouts."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
for name, source in json.loads((ROOT / "sources.lock.json").read_text()).items():
    dest = ROOT / "upstream" / name
    if not dest.exists():
        dest.mkdir(parents=True)
        subprocess.run(["git", "init", str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "remote", "add", "origin", source["url"]], check=True)
        subprocess.run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", source["rev"]], check=True)
        subprocess.run(["git", "-C", str(dest), "checkout", "--detach", "FETCH_HEAD"], check=True)
    actual = subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"], text=True).strip()
    if actual != source["rev"]:
        raise RuntimeError(f"{name}: expected {source['rev']}, found {actual}; refusing to reset")
