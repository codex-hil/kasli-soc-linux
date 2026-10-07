#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""ZC706 J5/CERN FMC ADC: 4-channel source-synchronous receiver and BRAM snapshot."""
import argparse
import json
from pathlib import Path
from migen import Cat, ClockDomain, ClockSignal, Instance, Signal, ResetSignal, If
from migen.genlib.cdc import MultiReg
from litex.gen import LiteXModule
from litex.build.generic_platform import Pins, Subsignal, IOStandard
from litex.soc.cores.clock import S7MMCM, S7IDELAYCTRL
from litex.soc.cores.bitbang import I2CMaster, SPIMaster
from litex.soc.interconnect.csr import CSR, CSRStorage, CSRStatus
from litex.soc.integration.export import get_csr_json
from kasli_soc import BaseSoC

ROOT = Path(__file__).resolve().parents[1]


def add_fmc_pads(platform):
    # Pinned CERN mezzanine mapping / official AMD package audit in evidence/zc706.
    audit = json.loads((ROOT / "evidence/zc706/fmc-adc-pin-audit-20261007.json").read_text())
    pins = {r["signal"].replace("%", ""): r["LPC"] for r in audit["pins"]}
    def pin(name):
        return pins["adc_" + name]
    def pair(name):
        return [Subsignal("p", Pins(pin(name + "_p_i"))),
                Subsignal("n", Pins(pin(name + "_n_i")))]
    platform.add_extension([
        ("adc_dco", 0, *pair("dco"), IOStandard("LVDS_25")),
        ("adc_frame", 0, *pair("fr"), IOStandard("LVDS_25")),
        ("adc_trigger", 0, *pair("ext_trigger"), IOStandard("LVDS_25")),
        ("adc_data", 0,
            Subsignal("p", Pins(" ".join(pin(f"out{lane}_p_i[{ch}]")
                for ch in range(4) for lane in ["b", "a"]))),
            Subsignal("n", Pins(" ".join(pin(f"out{lane}_n_i[{ch}]")
                for ch in range(4) for lane in ["b", "a"]))), IOStandard("LVDS_25")),
        ("adc_spi", 0,
            Subsignal("clk", Pins(pin("spi_sck_o"))),
            Subsignal("mosi", Pins(pin("spi_dout_o"))),
            Subsignal("miso", Pins(pin("spi_din_i"))),
            Subsignal("cs_n", Pins(pin("spi_cs_adc_n_o"))), IOStandard("LVCMOS25")),
        ("adc_i2c", 0, Subsignal("scl", Pins(pin("si570_scl_b"))),
            Subsignal("sda", Pins(pin("si570_sda_b"))), IOStandard("LVCMOS25")),
        ("adc_control", 0,
            Subsignal("osc_oe", Pins(pin("gpio_si570_oe_o"))),
            Subsignal("dac_clr_n", Pins(pin("gpio_dac_clr_n_o"))),
            Subsignal("dac_cs_n", Pins(" ".join(pin(f"spi_cs_dac{ch}_n_o") for ch in range(1, 5)))),
            Subsignal("ssr", Pins(" ".join(pin(f"gpio_ssr_ch{ch}_o[{bit}]")
                for ch in range(1, 5) for bit in range(7)))),
            Subsignal("led", Pins(pin("gpio_led_acq_o") + " " + pin("gpio_led_trig_o"))),
            IOStandard("LVCMOS25")),
    ])


class ADC(LiteXModule):
    def __init__(self, platform, ready):
        # reset, oscillator OE, external trigger, DAC clear release, DAC selects.
        self.control = CSRStorage(8, reset=1, name="control")
        self.arm = CSR(name="arm")
        self.status = CSRStatus(5, name="status")  # ready, aligned, busy, done, captured error
        self.frame = CSRStatus(8, name="frame")
        self.count = CSRStatus(32, name="count")
        self.captured = CSRStatus(11, name="captured")
        self.errors = CSRStatus(11, name="errors")
        self.read_address = CSRStorage(10, name="read_address")
        self.data_low = CSRStatus(32, name="data_low")
        self.data_high = CSRStatus(32, name="data_high")
        self.ssr = CSRStorage(28, name="ssr")  # default: disconnect analog inputs
        taps = []
        for lane in range(9):
            reg = CSRStorage(5, name=f"tap{lane}")
            setattr(self, f"tap{lane}", reg)
            taps.append(reg.storage)
        self.cd_adc = ClockDomain("adc")
        rx_reset, adc_reset = Signal(), Signal()
        aligned, frame, samples = Signal(), Signal(8), Signal(64)
        done, captured, errors, gray = Signal(), Signal(11), Signal(11), Signal(32)
        request, busy, complete = Signal(), Signal(), Signal()
        done_sys, aligned_sys, gray_sys = Signal(), Signal(), Signal(32)
        raw_frame, count_binary = Signal(8), Signal(32)
        # Gray counter avoids incoherent free-running multi-bit counter reads.
        self.specials += [MultiReg(done, done_sys), MultiReg(aligned, aligned_sys),
                          MultiReg(gray, gray_sys), MultiReg(frame, raw_frame)]
        decoded = gray_sys
        for shift in (1, 2, 4, 8, 16):
            decoded = decoded ^ (decoded >> shift)
        self.comb += count_binary.eq(decoded)
        # Snapshot count/errors are held after done; sample them only after CDC settles.
        settling = Signal(3)
        self.sync += If(self.control.storage[0],
            request.eq(0), busy.eq(0), complete.eq(0), settling.eq(0),
            self.captured.status.eq(0), self.errors.status.eq(0)
        ).Else(
            If(self.arm.re & ~busy,
                request.eq(~request), busy.eq(1), complete.eq(0), settling.eq(0)
            ),
            If(busy & (done_sys == request),
                If(settling == 7,
                    busy.eq(0), complete.eq(1),
                    self.captured.status.eq(captured), self.errors.status.eq(errors)
                ).Else(settling.eq(settling + 1))
            ).Else(settling.eq(0))
        )
        control = platform.request("adc_control")
        trigger_pads = platform.request("adc_trigger")
        trigger, trigger_adc = Signal(), Signal()
        self.specials += [Instance("IBUFDS", p_IOSTANDARD="LVDS_25", p_DIFF_TERM="TRUE",
                                  i_I=trigger_pads.p, i_IB=trigger_pads.n, o_O=trigger),
                          MultiReg(trigger, trigger_adc, "adc")]
        self.comb += [rx_reset.eq(ResetSignal() | self.control.storage[0] | ~ready),
            ResetSignal("adc").eq(adc_reset),
            control.osc_oe.eq(self.control.storage[1]), control.dac_clr_n.eq(self.control.storage[3]),
            control.dac_cs_n.eq(~self.control.storage[4:8]), control.ssr.eq(self.ssr.storage),
            control.led.eq(Cat(busy, complete)),
            self.status.status.eq(Cat(ready, aligned_sys, busy, complete, self.errors.status != 0)),
            self.frame.status.eq(raw_frame), self.count.status.eq(count_binary)]
        dco, fr, data = [platform.request(name) for name in ["adc_dco", "adc_frame", "adc_data"]]
        self.specials += Instance("fmc_adc_rx", i_dco_p=dco.p, i_dco_n=dco.n,
            i_frame_p=fr.p, i_frame_n=fr.n, i_data_p=data.p, i_data_n=data.n,
            i_sys_clk=ClockSignal(), i_reset=rx_reset, i_idelay_ready=ready,
            i_delay_taps=Cat(*taps), o_adc_clk=ClockSignal("adc"),
            o_adc_reset=adc_reset, o_samples=samples, o_frame=frame, o_aligned=aligned)
        read_data = Signal(64)
        self.specials += Instance("fmc_adc_capture", i_sys_clk=ClockSignal(),
            i_adc_clk=ClockSignal("adc"), i_reset=adc_reset,
            i_arm_toggle=request, i_ext_mode=self.control.storage[2], i_trigger=trigger_adc,
            i_aligned=aligned, i_frame=frame, i_samples=samples,
            i_read_address=self.read_address.storage, o_read_data=read_data,
            o_done_toggle=done, o_captured=captured, o_errors=errors, o_sample_gray=gray)
        self.comb += [self.data_low.status.eq(read_data[:32]),
                      self.data_high.status.eq(read_data[32:])]
        platform.add_period_constraint(dco.p, 2.5)
        platform.add_period_constraint(self.cd_adc.clk, 10.0)
        platform.add_source(str(ROOT / "gateware/fmc_adc_rx.v"))
        platform.add_source(str(ROOT / "gateware/fmc_adc_capture.v"))


class ADCSoC(BaseSoC):
    def add_csr_bridge(self, name="csr", origin=None, with_register=False):
        # Register the upstream bridge: the larger FMC CSR fanout otherwise
        # puts AXI burst-address arithmetic and bank decode on one long path.
        return super().add_csr_bridge(name, origin, with_register=True)

    def __init__(self):
        super().__init__("zc706")
        # Keep the physically validated probe ABI and identifier unchanged.
        self.csr.add("probe", 1)
        self.csr.add("adc", 2)
        self.csr.add("adc_spi", 3)
        self.csr.add("adc_i2c", 4)
        add_fmc_pads(self.platform)
        self.cd_idelay = ClockDomain("idelay")
        self.mmcm = S7MMCM(speedgrade=-2, fractional=False)
        self.comb += self.mmcm.reset.eq(ResetSignal())
        self.mmcm.register_clkin(ClockSignal(), 100e6)
        self.mmcm.create_clkout(self.cd_idelay, 200e6)
        self.idelayctrl = S7IDELAYCTRL(self.cd_idelay)
        ready_ref, ready = Signal(), Signal()
        # LiteX's helper supplies reset sequencing but leaves RDY unconnected.
        for special in self.idelayctrl._fragment.specials:
            if isinstance(special, Instance) and special.of == "IDELAYCTRL":
                special.items.append(Instance.Output("RDY", ready_ref))
        self.specials += MultiReg(ready_ref, ready)
        self.adc = ADC(self.platform, ready)
        self.adc_spi = SPIMaster(self.platform.request("adc_spi"))
        self.adc_i2c = I2CMaster(self.platform.request("adc_i2c"))
        self.add_constant("ADC_CAPTURE_SAMPLES", 1024)
        self.add_constant("ADC_SAMPLE_RATE", 100000000)
        self.add_constant("ADC_ABI", 1)
        self.platform.add_period_constraint(self.cd_idelay.clk, 5.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="build/zc706-adc/gateware")
    parser.add_argument("--board", choices=["zc706"], default="zc706")
    args = parser.parse_args()
    soc = ADCSoC()
    soc.finalize()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "csr.json").write_text(get_csr_json(csr_regions=soc.csr_regions,
        constants=soc.constants, mem_regions=soc.mem_regions))
    soc.platform.build(soc, build_dir=str(output / "gateware"), run=False)


if __name__ == "__main__":
    main()
