#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Dual WR PLL, independent ADC DMA, PL DDR and SFP Ethernet."""
import argparse
from pathlib import Path
from zc706_adc_ddr import ADCDDRSoC
from zc706_ddr import export_soc, SYS_CLK_FREQ
from zc706_sfp import add_sfp
from reciprocal import ReciprocalCounter
from wr_pll import WRPhase

class IntegratedSoC(ADCDDRSoC):
    def __init__(self):
        super().__init__()
        for bank, name, domain in ((16,'frequency','adc'),
                                  (17,'frequency2','adc2'),
                                  (18,'frequency_reference','sys')):
            self.csr.add(name, bank)
            setattr(self, name, ReciprocalCounter(self.platform, domain,
                                                 reference_hz=round(SYS_CLK_FREQ)))
        self.csr.add('wr_phase',19)
        self.csr.add('wr_phase2',20)
        self.wr_phase = WRPhase(self.platform, reference_domain='ps7')
        self.wr_phase2 = WRPhase(self.platform, adc_domain='adc2',
            helper_locked=self.wr_phase.helper_mmcm.locked, reference_domain='ps7')
        for name,value in dict(WR_PHASE_ABI=1,WR_PHASE_CARDS=2,
                WR_DDMTD_HELPER_NUMERATOR=63,WR_DDMTD_HELPER_DENOMINATOR=64,
                RECIPROCAL_ABI=1,RECIPROCAL_REFERENCE_HZ=round(SYS_CLK_FREQ),
                RECIPROCAL_CLOCK_ONLY=0,INTEGRATED_ABI=1).items():
            self.add_constant(name,value)
        add_sfp(self, sys_clk_freq=SYS_CLK_FREQ, bank=21)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--board',choices=['zc706'],default='zc706')
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args(); soc=IntegratedSoC();soc.finalize()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    export_soc(soc,a.output_dir)

if __name__=='__main__':main()
