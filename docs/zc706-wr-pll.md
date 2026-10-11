# ZC706 White Rabbit phase PLL development

This is a bounded, clock-only development target. It leaves ADC acquisition,
FIFO and PL DDR out of the design. FMC1 (J5 LPC) is the controlled oscillator;
FMC2 (J4 HPC) remains an independent, untuned control. The reference is the
100 MHz PS FCLK, not an externally calibrated laboratory reference.

## Architecture and provenance

PS FCLK → MMCM helper at 100 MHz × 63/64 → original CERN WR DDMTD taggers
→ continuous phase unwrapping → coherent LiteX CSR snapshot → Linux WR-derived
integer PI → Si570 RFREQ. Independent reciprocal counters verify both cards
and a reference self-check while the phase loop runs.

The original `dmtd_sampler.vhd` and `dmtd_with_deglitcher.vhd` are translated
with GHDL without editing their upstream source. `sources.lock.json` pins
WR cores, WRPC software and the matching general-cores revision. The generated
RTL manifest records every source hash and GHDL version/options. FPGA synthesis,
placement, routing and bitstream generation use Yosys/nextpnr/openXC7.
Vivado is not required.

`tools/wr_pll_control.py` ports the integer, saturating anti-windup update from
WRPC `softpll/spll_common.c`; attribution and GPL-2 license are retained.
WR DDMTD is LGPL-2.1-or-later; general-cores is Solderpad-2.0.
The LiteX wrapper and phase tracker are BSD-2-Clause.

The helper produces a beat every 64 reference cycles (63 helper ticks).
One phase tick represents 10/63 ns. Hardware continuously unwraps phase, so
slow software polling does not conceal whole-cycle slips. Missing clock tags
invalidate phase within 100 µs. CSR bank 12 provides reset (asserted at boot),
snapshot, signature, status, signed phase/raw phase, event/rejection counters
and the ages of both tag streams. Helper locked and phase valid are status
bits 0 and 1.

## Reproduction and safe physical tests

Start with the existing ZC706 Linux/toolchain preparation in the main README.
The ZC706 Buildroot cross compiler is reused for the native I²C backend:

```sh
make wr-pll-sim
make wr-pll-pl
make wr-pll-software
.venv/bin/python tools/boot_adc_jtag.py --host BOARD_IP --sd \
  --bit build/zc706-wr-pll/gateware/gateware/top.bit \
  --output build/zc706-wr-pll/boot
python3 tools/test_wr_pll.py --host BOARD_IP --seconds 60 --loss-test
```

The host runner takes the shared ZC706 lock, uploads the matching CSR map and
records source/bitstream hashes. Si570 tuning is restricted to ±50 ppm around
the initial RFREQ; HSDIV/N1 remain unchanged. Small updates use Freeze M,
RFREQ writes, and unfreeze, with ACK, clock-stretch timeout and readback checks.
Si570 supports Fast-mode I²C up to 400 kbit/s ([vendor datasheet](https://www.skyworksinc.com/-/media/skyworks/sl/documents/public/data-sheets/si570-71.pdf)).
The native C transport enforces at least 1.5 µs per line state. It avoids Python
bitbang overhead while keeping the same transaction checks. No Freeze DCO,
NewFreq, OTP or boot-flash writes are used. Factory RFREQ is restored and
phase reset asserted on both success and failure. Tests are finite; no
background servo is left running.

## Status and evidence

Original WR DDMTD simulation passes a +10 ppm clock with exact -20 ns phase
drift over 2 ms, including several clock-period wraps. The physical clock-only
bitstream passes setup and hold timing and boots with Linux/SSH. Physical
Si570 ±5 ppm tuning produced a measured 10.080273 ppm span; the original
registers were restored. Constant ±1 ppm tuning produces approximately
∓1000 ns/s measured phase drift, confirming physical sign and scale.

**FMC1 phase PLL prototype: physically validated.** Two 60-second runs passed,
separated by an oscillator-output disable/re-enable and fresh acquisition.
The acceptance window is the last 20 seconds of each run: every sampled phase
must remain within ±10 ns, standard deviation below 3 ns, mean phase within
±1 ns, and more than 95% of polls must report lock. Lock requires 30 consecutive
valid samples within ±10 ns. This is a prototype criterion, not a claim of
subnanosecond White Rabbit timing or a jitter qualification.

| Measurement, final 20 s | Initial | After clock loss/reacquisition |
|---|---:|---:|
| Mean DDMTD phase | +0.00192 ns | +0.02227 ns |
| Phase standard deviation | 2.20327 ns | 2.28882 ns |
| Minimum phase | −7.14286 ns | −8.73016 ns |
| Maximum phase | +8.73016 ns | +8.25397 ns |
| Lock fraction | 100% | 100% |
| Median software update interval | 4.9212 ms | 4.9233 ms |
| Mean reciprocal frequency error | approximately 0 ppm | −0.0005 ppm |
| Untuned FMC2 frequency error | +15.0812 ppm | +14.9987 ppm |

The helper remained locked during clock loss, while phase validity cleared.
FMC2 oscillator registers remained unchanged. FMC1's original RFREQ was
verified after restoration; phase reset is asserted at test exit. The working
bitstream stays loaded, but the bounded test leaves no background servo.
Re-run the command above to acquire and hold phase again.

The PI uses Kp = 0.1 ppm/ns and Ki = 0.3 ppm/(ns·s), with Ki scaled by the
actual update interval. Output changes are limited to 1 ppm per update and
RFREQ remains within ±50 ppm of its initial setting. The software watches
helper lock, tag freshness, rejected events, phase escape and independent
reciprocal counters. Initial frequency acquisition uses three one-second
reciprocal windows before phase control starts.

The first experiments used a stricter ±1 ns criterion and failed it. Faster
I²C reduced oscillations substantially; the final measured performance above
is qualified against the explicitly stated prototype limits. Failed-run
statistics and identities are retained in the evidence, not counted as passes.

[Physical evidence](../evidence/zc706/wr-pll-20261011/hardware-validation.json)
includes matched source/bitstream hashes, frequency windows, clock-loss state,
boot record and compressed full phase records. The ZC706 Linux clock starts
at Unix epoch, so host UTC timestamps identify the actual test time.
The qualified bitstream SHA-256 is
`8524d9883b768e15f27ddf421da5903006e225271fc7fa019b5da5ce39acad60`.
Use `make wr-pll-package` to bundle its matched bitstream, CSR map, software,
original DDMTD VHDL, licenses and evidence. Packaging refuses mismatched or
unqualified artifacts.

FMC2 regulation, an external clock reference, absolute phase calibration,
phase-noise/jitter characterization and integration with ADC capture remain
pending. Full WR networking and time transfer are outside this clock PLL PoC.
