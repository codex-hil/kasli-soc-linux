#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Small SRL16E versus observable flip-flop reference diagnostic."""
import argparse
from pathlib import Path
from migen import Cat, ClockSignal, Constant, If, Instance, Signal
from litex.gen import LiteXModule
from litex.soc.integration.export import get_csr_json
from litex.soc.interconnect.csr import CSRStatus, CSRStorage
from kasli_soc import BaseSoC
from zc706_sfp import SFPClock


class SRLDiagnostic(LiteXModule):
    def __init__(self):
        self.signature = CSRStatus(32, reset=0x53524c33, name="signature")
        self.cycles = CSRStatus(32, name="cycles")
        self.errors = CSRStatus(32, name="errors")
        self.ready = CSRStatus(1, name="ready")
        # Runtime polarity prevents Yosys from merging the inferred chain
        # into the fully observable reference. Keep it fixed while measuring.
        self.polarity = CSRStorage(1, name="polarity")
        self.reference4 = CSRStatus(32, name="reference4")
        self.reference8 = CSRStatus(64, name="reference8")
        lfsr = Signal(16, reset=0x1234)
        warmup = Signal(5)
        self.comb += self.ready.status.eq(warmup == 16)
        self.sync += [
            lfsr.eq(Cat(lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10], lfsr[:15])),
            self.cycles.status.eq(self.cycles.status + 1),
            If(warmup != 16, warmup.eq(warmup + 1))]
        for bank, depth in enumerate((4, 8)):
            reference = Signal(depth * 8, name="reference_depth" + str(depth))
            inferred = Signal(depth * 8, reset_less=True,
                              name="inferred_depth" + str(depth))
            explicit_raw = Signal(8)
            explicit = Signal(8)
            masked = Signal(8)
            self.comb += [masked.eq(lfsr[:8] ^ (self.polarity.storage * 255)),
                getattr(self, "reference" + str(depth)).status.eq(reference)]
            self.sync += [reference.eq(Cat(lfsr[:8], reference[:-8])),
                inferred.eq(Cat(masked, inferred[:-8])),
                explicit.eq(explicit_raw)]
            expected = reference[-8:]
            # Low16: inferred chains. High16: explicit SRL + final FF.
            mismatch = Signal(8)
            explicit_mismatch = Signal(8)
            self.comb += [
                mismatch.eq(inferred[-8:] ^ expected ^ (self.polarity.storage * 255)),
                explicit_mismatch.eq(explicit ^ expected)]
            self.sync += If(self.ready.status,
                self.errors.status[bank*8:bank*8+8].eq(
                    self.errors.status[bank*8:bank*8+8] | mismatch),
                self.errors.status[16+bank*8:24+bank*8].eq(
                    self.errors.status[16+bank*8:24+bank*8] | explicit_mismatch))
            # Yosys usually leaves the last FF outside SRL extraction.
            tap = depth - 2
            for lane in range(8):
                self.specials += Instance("SRL16E", p_INIT=0,
                    i_CLK=ClockSignal("sys"), i_CE=Constant(1), i_D=lfsr[lane],
                    i_A0=Constant(tap & 1), i_A1=Constant((tap >> 1) & 1),
                    i_A2=Constant((tap >> 2) & 1), i_A3=Constant((tap >> 3) & 1),
                    o_Q=explicit_raw[lane])



class SRLSoC(BaseSoC):
    def __init__(self):
        super().__init__("zc706", crg=SFPClock(), sys_clk_freq=50e6)
        self.cpu.cpu_params["i_M_AXI_GP0_ACLK"] = ClockSignal("sys")
        self.csr.add("probe", 1)
        self.srl = SRLDiagnostic()
        self.csr.add("srl", 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", choices=["zc706"], default="zc706")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    soc = SRLSoC()
    soc.finalize()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "csr.json").write_text(get_csr_json(
        csr_regions=soc.csr_regions, constants=soc.constants,
        mem_regions=soc.mem_regions))
    soc.platform.build(soc, build_dir=str(output / "gateware"), run=False)


if __name__ == "__main__":
    main()
