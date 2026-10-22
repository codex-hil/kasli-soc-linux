# SPDX-License-Identifier: BSD-2-Clause
"""Scoped, pinned LiteX beat-pipeline overlay; never edits the source checkout."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]


def candidate_class():
    import litex.soc.interconnect.axi.axi_full_to_axi_lite as upstream
    source = Path(upstream.__file__)
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)/'axi_full_to_axi_lite.py'
        subprocess.run(['patch', '--silent', '--fuzz=0', '--output', str(output),
            str(source), str(ROOT/'patches/litex-axi-beat-buffer.patch')], check=True)
        module = types.ModuleType('zc706_axi_beat_overlay')
        exec(compile(output.read_text(), str(source), 'exec'), module.__dict__)
    return module.AXI2AXILite


@contextmanager
def buffered_axi_beats():
    import litex.soc.interconnect.axi as axi
    import litex.soc.interconnect.axi.axi_full_to_wishbone as wishbone
    candidate = candidate_class()
    def buffered(*args, **kwargs):
        return candidate(*args, buffer_beats=True, **kwargs)
    previous = axi.AXI2AXILite, wishbone.AXI2AXILite
    axi.AXI2AXILite = wishbone.AXI2AXILite = buffered
    try:
        yield buffered
    finally:
        axi.AXI2AXILite, wishbone.AXI2AXILite = previous
