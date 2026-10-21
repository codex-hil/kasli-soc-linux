#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Small SRL16E versus observable flip-flop reference diagnostic."""
import argparse
from pathlib import Path
from migen import Cat, ClockSignal, Constant, If, Instance, Signal
from litex.gen import LiteXModule
from litex.soc.integration.export import get_csr_json
from litex.soc.interconnect.csr import CSRStatus
from kasli_soc import BaseSoC
from zc706_sfp import SFPClock


class SRLDiagnostic(LiteXModule):
    def __init__(self):
        self.signature = CSRStatus(32, reset=0x53524c31, name="signature")
        self.cycles = CSRStatus(32, name="cycles")
        self.errors = CSRStatus(16, name="errors")
        self.outputs = CSRStatus(16, name="outputs")
        self.expected = CSRStatus(16, name="expected")
        self.reference = CSRStatus(16, name="reference")
        self.ready = CSRStatus(1, name="ready")
        # All reference bits are externally observed, preventing SRL inference.
        reference = Signal(16, reset=0xa69c)
        lfsr = Signal(16, reset=0x1234)
        divider = Signal(4)
        enabled = Signal(5)
        ce = Signal()
        data = lfsr[0]
        self.comb += [ce.eq(divider != 3), self.reference.status.eq(reference),
                     self.expected.status.eq(reference),
                     self.ready.status.eq(enabled == 16)]
        self.sync += [divider.eq(divider + 1),
            lfsr.eq(Cat(lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10], lfsr[:15])),
            self.cycles.status.eq(self.cycles.status + 1),
            If(ce, reference.eq(Cat(data, reference[:15])),
               If(enabled != 16, enabled.eq(enabled + 1))),
            If(self.ready.status,
               self.errors.status.eq(self.errors.status |
                   (self.outputs.status ^ reference)))]
        for tap in range(16):
            self.specials += Instance("SRL16E", p_INIT=0xa69c,
                i_CLK=ClockSignal("sys"), i_CE=ce, i_D=data,
                i_A0=Constant(tap & 1), i_A1=Constant((tap >> 1) & 1),
                i_A2=Constant((tap >> 2) & 1), i_A3=Constant((tap >> 3) & 1),
                o_Q=self.outputs.status[tap])


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
