#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Small clock-only development target: no ADC deserializer, BRAM, FIFO or DDR."""
import argparse
import json
from pathlib import Path
from migen import ClockDomain, ClockSignal, Signal, Instance
from litex.gen import LiteXModule
from litex.soc.cores.bitbang import I2CMaster, SPIMaster
from litex.soc.interconnect.csr import CSRStorage, CSRStatus
from litex.soc.integration.export import get_csr_json
from kasli_soc import BaseSoC
from fmc_adc import ADCCRG, add_fmc_pads
from reciprocal import ReciprocalCounter


class FMCClock(LiteXModule):
    def __init__(self, platform, index):
        # Retain only the board control subset used by ADC.initialize().
        # All analog SSR inputs default disconnected; DAC chip selects inactive.
        self.control = CSRStorage(8, reset=1, name="control")
        self.ssr = CSRStorage(28, name="ssr")
        self.card_id = CSRStatus(32, reset=0xadc00001+index, name="card_id")
        pads = platform.request("adc_control", index)
        self.comb += [pads.osc_oe.eq(self.control.storage[1]),
            pads.dac_clr_n.eq(self.control.storage[3]),
            pads.dac_cs_n.eq(~self.control.storage[4:8]),
            pads.ssr.eq(self.ssr.storage), pads.led.eq(0)]
        domain = "adc" if index == 0 else "adc2"
        raw_domain = "dco" if index == 0 else "dco2"
        self.cd_dco = ClockDomain(raw_domain, reset_less=True)
        self.cd_adc = ClockDomain(domain, reset_less=True)
        dco = platform.request("adc_dco", index)
        raw, divided = Signal(), Signal(2)
        self.specials += [Instance("IBUFDS", p_IOSTANDARD="LVDS_25", p_DIFF_TERM="TRUE",
            i_I=dco.p, i_IB=dco.n, o_O=raw),
            Instance("BUFG", i_I=raw, o_O=ClockSignal(raw_domain)),
            Instance("BUFG", i_I=divided[1], o_O=ClockSignal(domain))]
        # Two flip-flops divide the physical 400 MHz DCO by four. No MMCM,
        # IDELAYCTRL, ISERDES or data path is required to measure sample rate.
        if index == 0:
            self.sync.dco += divided.eq(divided+1)
        else:
            self.sync.dco2 += divided.eq(divided+1)
        platform.add_period_constraint(self.cd_dco.clk, 2.5)
        platform.add_period_constraint(self.cd_adc.clk, 10.0)


class FrequencySoC(BaseSoC):
    def add_csr_bridge(self, name="csr", origin=None, with_register=False):
        return super().add_csr_bridge(name, origin, with_register=True)

    def __init__(self):
        super().__init__("zc706", crg=ADCCRG())
        self.cpu.cpu_params["i_M_AXI_GP0_ACLK"] = ClockSignal("sys")
        self.csr.add("probe", 1)
        for index, name in enumerate(("adc", "adc2")):
            add_fmc_pads(self.platform, index=index, slot="LPC" if index == 0 else "HPC")
            self.csr.add(name, 2 if index == 0 else 6)
            self.csr.add(name+"_spi", 3 if index == 0 else 7)
            self.csr.add(name+"_i2c", 4 if index == 0 else 8)
            setattr(self, name, FMCClock(self.platform, index))
            setattr(self, name+"_spi", SPIMaster(self.platform.request("adc_spi", index)))
            setattr(self, name+"_i2c", I2CMaster(self.platform.request("adc_i2c", index)))
            counter = "frequency" if index == 0 else "frequency2"
            self.csr.add(counter, 9+index)
            setattr(self, counter, ReciprocalCounter(self.platform, name))
        self.csr.add("frequency_reference", 11)
        self.frequency_reference = ReciprocalCounter(self.platform, "sys")
        for name, value in dict(ADC_ABI=1, ADC_CARDS=2, ADC_FPGA_DIFF_TERM=1,
                RECIPROCAL_ABI=1, RECIPROCAL_REFERENCE_HZ=100000000,
                RECIPROCAL_CLOCK_ONLY=1, RECIPROCAL_DCO_DIVIDER=4).items():
            self.add_constant(name, value)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--board", choices=["zc706"], default="zc706")
    p.add_argument("--output-dir", default="build/zc706-frequency-small/gateware")
    a = p.parse_args()
    soc = FrequencySoC()
    soc.finalize()
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out/"csr.json").write_text(get_csr_json(csr_regions=soc.csr_regions,
        constants=soc.constants, mem_regions=soc.mem_regions))
    soc.platform.build(soc, build_dir=str(out/"gateware"), run=False)


if __name__ == "__main__":
    main()
