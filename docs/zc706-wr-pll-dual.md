# Two independent FMC clock PLLs on ZC706

The dual target disciplines both CERN FMC ADC Si570 oscillators to nominal
100 MHz PS FCLK0. FMC1 is J5 LPC; FMC2 is J4 HPC. The two independent DCO
inputs are divided from 400 MHz to 100 MHz. One shared 98.4375 MHz helper
MMCM clocks two independent original CERN WR DDMTD tagger pairs and phase
trackers. Each pair has its own reference tagger, reset, snapshot and continuous
phase unwrapping. Resetting or losing one FMC stream does not reset the other
phase detector or the shared helper.

The existing FMC1 target and its qualified release are retained separately.
The dual build uses `build/zc706-wr-pll-dual`; bank 12 is `wr_phase` (FMC1),
bank 13 is `wr_phase2` (FMC2). `WR_PHASE_ABI=1` and `WR_PHASE_CARDS=2` identify
the CSR interface. Registers have the same meanings as the
[single-loop target](zc706-wr-pll.md). ADC reception, FIFOs and PL DDR are
omitted from this development target.

`run_wr_pll_dual.py` owns both reciprocal-counter gates, avoiding races between
independent regulator processes. Every Si570 has a separate RFREQ anchor and
PI integrator. Each PI uses its own measured update interval. Updates are
serialized through the checked native I²C backend; neither ADC clock
is used as a timing reference for the other. Both clocks are compared directly
to PS FCLK. This is a sampled phase-loop prototype; external reference,
absolute phase calibration and phase-noise qualification remain separate work.

The native backend can time line states using `probe_counter` at SYS = 100 MHz:
at least 150 ticks (1.5 µs), with unsigned wrap handling. It retains the CPU-timed
ABI for older bundles or different SYS frequencies. SCL stretch and a stalled
PL timer have bounded timeouts; both open-drain lines are released on failure.
NACK, invalid offsets and both timeout paths are covered with simulated-MMIO
software tests. The physical phase loop uses Kp = 0.10 ppm/ns on FMC1,
0.15 ppm/ns on FMC2 and Ki = 0.30 ppm/(ns·s) on each card. FMC2's larger
observed phase wander motivated the separate proportional gain; test limits
remain the same for both cards.

## Build and physical qualification

Use the existing ZC706 Linux and openXC7 setup in the main README, then:

```sh
make wr-pll-dual-sim
make wr-pll-dual-pl wr-pll-dual-software
# Sync Linux, reset PS, load volatile PL through JTAG, and boot existing SD.
.venv/bin/python tools/boot_adc_jtag.py --host BOARD_IP \
  --bit build/zc706-wr-pll-dual/gateware/gateware/top.bit \
  --output build/zc706-wr-pll-dual/boot
# DHCP may assign a new address: use the host reported by the boot script.
python3 tools/test_wr_pll.py --host NEW_BOARD_IP --dual --control fmc2 \
  --seconds 60 --loss-test --output build/zc706-wr-pll-dual/fmc2-only
python3 tools/test_wr_pll.py --host NEW_BOARD_IP --dual --control both \
  --seconds 60 --loss-test --output build/zc706-wr-pll-dual/both
```

The first test controls FMC2 only and verifies FMC1's original Si570 registers
remain unchanged. The second holds both phase loops, tests isolated clock loss
on FMC1 and then on FMC2, and repeats phase-hold qualification after each
reacquisition. During each loss, the other detector must remain valid and its
phase event counter must advance. The helper must remain locked, while only
the lost stream's phase validity clears.

Tests take the shared ZC706 lock, are bounded and restore both initial RFREQ
settings on exit. Restoration of one card is attempted even if restoration of
the other fails, and each phase reset is asserted independently. Restoration
errors invalidate qualification and are recorded. Partial measurements are
retained on failure. No background servo is left running. No boot-flash,
OTP or permanent U-Boot environment writes are used.

Acceptance is unchanged from the single-loop prototype: in the final 20 s,
all sampled phases within ±10 ns, phase standard deviation below 3 ns, mean
within ±1 ns, and more than 95% lock fraction (30 consecutive valid samples
inside ±10 ns to assert lock). Independent one-second reciprocal gates check
both frequencies and the exact 1:1 reference self-check. This criterion does
not claim subnanosecond WR time transfer.

## Current status

Dual WR DDMTD simulation passed +10/-8 ppm clocks, multiple phase wraps,
isolated loss, independent reset and recovery. Yosys/nextpnr/openXC7 build
passed setup and hold; the physical JTAG-loaded target boots Linux/SSH.
FMC2-only phase hold and isolated clock-loss/reacquisition passed two
60-second runs. Final 20-second phase statistics: standard deviation
2.16108/2.00027 ns; peaks within ±8.09524 ns; lock fraction 100% in both
windows. FMC1 Si570 registers remained unchanged and its DDMTD detector
continued during FMC2 clock loss. Initial settings were restored on both cards.
[Evidence](../evidence/zc706/wr-pll-dual-20261011/fmc2-only/hardware-validation.json).
Simultaneous dual-loop qualification is in progress.

DCO÷4 phase hold establishes a common frequency and monitored phase reference.
ADC framing, cable/PCB delay calibration and physical simultaneous sample-phase
validation remain pending when the clock logic is integrated with acquisition.
