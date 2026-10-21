#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Dual WR PLL, independent ADC DMA, PL DDR and SFP Ethernet."""
import argparse
from pathlib import Path
from migen import Signal, Instance, ClockSignal, ResetSignal
from zc706_adc_ddr import ADCDDRSoC
from zc706_ddr import export_soc, SYS_CLK_FREQ
from zc706_sfp import add_sfp
from reciprocal import ReciprocalCounter
from wr_pll import WRPhase

class IntegratedSoC(ADCDDRSoC):
    def __init__(self, refclk="fclk", ddr_sync_reset=False, header_probes=True):
        super().__init__()
        if ddr_sync_reset:
            # One shared release edge for all DDR input/output serializers.
            # Assertion remains asynchronous; deassertion waits two SYS edges.
            raw = ResetSignal("sys") | self.ddrphy._rst.storage
            first = Signal(reset=1, name="ddr_serdes_reset_first")
            released = Signal(reset=1, name="ddr_serdes_reset_sync")
            for name, source, destination in (
                    ("ddr_reset_sync0", 0, first),
                    ("ddr_reset_sync1", first, released)):
                register = Instance("FDPE", name=name, p_INIT=1,
                    i_C=ClockSignal("sys"), i_CE=1, i_PRE=raw,
                    i_D=source, o_Q=destination)
                register.attr.add(("ASYNC_REG", "TRUE"))
                register.attr.add(("DONT_TOUCH", "TRUE"))
                self.specials += register
            changed = 0
            for special in self.ddrphy._fragment.specials:
                if isinstance(special, Instance) and special.of in ("ISERDESE2", "OSERDESE2"):
                    for item in special.items:
                        if isinstance(item, Instance.Input) and item.name == "RST":
                            item.expr = released
                            changed += 1
            if changed != 171:
                raise RuntimeError(f"Unexpected DDR serializer count: {changed}")
            self.add_constant("DDR_SERDES_SYNC_RESET", 1)

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
        add_sfp(self, refclk=refclk, sys_clk_freq=SYS_CLK_FREQ, bank=21, register_usrready=False, clock_monitors=False, header_probes=header_probes)
        # Retain qualified SFP TX clock placement and all SFP BUFG sites.
        # RX and ADC2 share the upper left clock column on integration.
        # Unconstrained TX at X0Y0 could not route CLKOUT1 to its BUFG.
        for cell,site in [('MMCME2_ADV_2','MMCME2_ADV_X0Y2'),
                          ('MMCME2_ADV_3','MMCME2_ADV_X0Y4'),
                          ('MMCME2_ADV_1','MMCME2_ADV_X1Y5'),
                          ('adc_rx.dco_mmcm','MMCME2_ADV_X0Y1'),
                          ('adc2_rx.dco_mmcm','MMCME2_ADV_X0Y3'),
                          ('BUFH','BUFGCTRL_X0Y0'),
                          ('BUFH_1','BUFGCTRL_X0Y8'),
                          ('BUFH_2','BUFGCTRL_X0Y7'),
                          ('BUFG_5','BUFGCTRL_X0Y6'),
                          ('BUFG_6','BUFGCTRL_X0Y21'),
                          ('BUFG_7','BUFGCTRL_X0Y16'),
                          ]:
            self.platform.add_platform_command(
                f'set_property LOC {site} [get_cells {cell}]')

    def _finalize_csr(self):
        super()._finalize_csr()
        from csr_address_replication import CSRAddressReplication
        if len(self.csr.masters) != 1:
            raise RuntimeError('CSR address replication requires one registered master')
        self.csr_address_replication = CSRAddressReplication(
            self.csr_bridge, self.csr_interconnect, self.csr_bankarray.get_buses())

    def do_finalize(self):
        super().do_finalize()
        # Capture each asynchronous LOCKED output adjacent to its hard macro.
        # All existing consumers (reset sequencers, READY and diagnostics) use
        # the synchronized value; SYS remains independent of these MMCMs.
        for name, mmcm, site in (
                ('sfp_tx',self.ethphy.tx_mmcm,('SLICE_X0Y108','SLICE_X1Y108')),
                ('sfp_rx',self.ethphy.rx_mmcm,('SLICE_X0Y208','SLICE_X1Y208'))):
            raw, first = Signal(name=name+'_lock_raw'), Signal(name=name+'_lock_first')
            instances=[special for special in mmcm._fragment.specials
                if isinstance(special,Instance) and special.of=='MMCME2_ADV']
            if len(instances)!=1:raise RuntimeError('Expected finalized SFP MMCM')
            changed=0
            for item in instances[0].items:
                if isinstance(item,Instance.Output) and item.name=='LOCKED':
                    item.expr=raw;changed+=1
            if changed!=1:raise RuntimeError('Expected one MMCM LOCKED output')
            for index,(source,destination) in enumerate(((raw,first),(first,mmcm.locked))):
                cell=name+'_lock_sync'+str(index)
                register=Instance('FDRE',name=cell,p_INIT=0,i_C=ClockSignal('sys'),
                    i_CE=1,i_R=ResetSignal('sys'),i_D=source,o_Q=destination)
                register.attr.add(('ASYNC_REG','TRUE'))
                register.attr.add(('DONT_TOUCH','TRUE'))
                self.specials += register
                self.platform.add_platform_command(
                    f'set_property LOC {site[index]} [get_cells {cell}]')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--board',choices=['zc706'],default='zc706')
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--refclk',choices=['fclk','si5324'],default='fclk')
    p.add_argument("--ddr-sync-reset", action="store_true")
    p.add_argument("--no-header-probes", action="store_true")
    a=p.parse_args(); soc=IntegratedSoC(a.refclk, a.ddr_sync_reset, not a.no_header_probes);soc.finalize()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    export_soc(soc,a.output_dir)

if __name__=='__main__':main()
