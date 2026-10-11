# SPDX-License-Identifier: BSD-2-Clause
"""LiteX integration of original CERN WR DDMTD taggers, with coherent snapshots."""
from pathlib import Path
from migen import Signal, ClockDomain, ClockSignal, ResetSignal, Instance, If, Cat
from migen.genlib.cdc import MultiReg
from litex.gen import LiteXModule
from litex.soc.cores.clock import S7MMCM
from litex.soc.interconnect.csr import CSR, CSRStorage, CSRStatus


class WRPhase(LiteXModule):
    def __init__(self, platform, adc_domain='adc', helper_locked=None):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
        from build_wr_ddmtd import prepare
        platform.add_source(str(prepare()))
        platform.add_source(str(Path(__file__).with_name('wr_phase_tracker.v')))
        if helper_locked is None:
            self.cd_helper = ClockDomain('helper')
            self.helper_mmcm = S7MMCM(speedgrade=-2, fractional=False)
            self.comb += self.helper_mmcm.reset.eq(ResetSignal())
            self.helper_mmcm.register_clkin(ClockSignal(), 100e6)
            self.helper_mmcm.create_clkout(self.cd_helper, 100e6*63/64, margin=0)
            platform.add_period_constraint(self.cd_helper.clk, 1e9/(100e6*63/64))
            helper_locked = self.helper_mmcm.locked
        self.signature = CSRStatus(32, reset=0x57525031, name='signature')
        self.reset = CSRStorage(1, reset=1, name='reset')
        self.snapshot = CSR(name='snapshot')
        self.status = CSRStatus(2, name='status')
        self.phase = CSRStatus(32, name='phase')
        self.raw_phase = CSRStatus(32, name='raw_phase')
        self.events = CSRStatus(32, name='events')
        self.rejected = CSRStatus(32, name='rejected')
        self.ref_age = CSRStatus(32, name='ref_age')
        self.adc_age = CSRStatus(32, name='adc_age')
        reset_helper = Signal()
        self.specials += MultiReg(self.reset.storage, reset_helper, odomain='helper')
        tags, strobes = [], []
        for domain in ('sys', adc_domain):
            tag, strobe = Signal(32), Signal()
            tags.append(tag); strobes.append(strobe)
            self.specials += Instance('dmtd_with_deglitcher',
                i_rst_n_dmtdclk_i=~(ResetSignal('helper') | reset_helper),
                i_rst_n_sysclk_i=~(ResetSignal() | self.reset.storage),
                i_clk_in_i=ClockSignal(domain), i_clk_dmtd_i=ClockSignal('helper'),
                i_clk_dmtd_over_i=0, i_clk_sys_i=ClockSignal(),
                i_clk_sampled_a_i=0, i_resync_p_a_i=0, i_resync_p_over_i=0,
                i_r_deglitch_threshold_i=4, i_r_oversample_in_div_i=0,
                i_r_oversample_pps_div_i=0, i_r_samples_i=0, i_r_minmax_sel_i=0,
                i_r_stat_reset_i=0, i_pps_p1_i=0, o_tag_o=tag, o_tag_stb_p1_o=strobe)
        values = [Signal(32) for _ in range(6)]
        valid, locked = Signal(), Signal()
        self.specials += MultiReg(helper_locked, locked)
        self.specials += Instance('wr_phase_tracker', i_clk=ClockSignal(),
            i_reset=ResetSignal() | self.reset.storage | ~locked,
            i_ref_strobe=strobes[0], i_adc_strobe=strobes[1],
            i_ref_tag=tags[0], i_adc_tag=tags[1], o_valid=valid,
            **dict(zip(('o_phase_ticks','o_raw_ticks','o_events','o_rejected','o_ref_age','o_adc_age'),values)))
        self.sync += If(self.snapshot.re,
            self.status.status.eq(Cat(locked, valid)),
            *[reg.status.eq(value) for reg,value in zip(
                (self.phase,self.raw_phase,self.events,self.rejected,self.ref_age,self.adc_age),values)])
