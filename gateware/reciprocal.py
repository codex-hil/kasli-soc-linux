# SPDX-License-Identifier: BSD-2-Clause
"""Reciprocal measurement against the caller's system-clock reference."""
from pathlib import Path
from migen import ClockSignal, ResetSignal, Instance, Signal, Cat
from litex.gen import LiteXModule
from litex.soc.interconnect.csr import CSRStorage, CSRStatus, CSR


class ReciprocalCounter(LiteXModule):
    def __init__(self, platform, measured_domain, reference_hz=100000000):
        self.gate = CSRStorage(32, reset=100000000, name="gate")
        self.reset = CSRStorage(1, reset=1, name="reset")
        self.start = CSR(name="start")
        self.signature = CSRStatus(32, reset=0x52464331, name="signature")
        self.status = CSRStatus(4, name="status")
        self.reference_ticks = CSRStatus(32, name="reference_ticks")
        self.measured_cycles = CSRStatus(32, name="measured_cycles")
        self.sequence = CSRStatus(32, name="sequence")
        busy, valid, error = Signal(), Signal(), Signal(2)
        self.comb += self.status.status.eq(Cat(busy, valid, error))
        self.specials += Instance("reciprocal_counter",
            p_TIMEOUT_TICKS=3*reference_hz,
            i_ref_clk=ClockSignal(), i_measured_clk=ClockSignal(measured_domain),
            i_reset=ResetSignal() | self.reset.storage,
            i_start=self.start.re, i_gate_cycles=self.gate.storage,
            o_busy=busy, o_valid=valid, o_error=error,
            o_reference_ticks=self.reference_ticks.status,
            o_measured_cycles=self.measured_cycles.status,
            o_sequence_id=self.sequence.status)
        platform.add_source(str(Path(__file__).with_name("reciprocal_counter.v")))
