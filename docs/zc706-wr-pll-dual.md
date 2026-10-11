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
independent regulator processes. Each Si570 has its own RFREQ anchor and PI
integrator, and each PI uses its measured update interval. The main thread owns
phase snapshots and PI updates; two worker threads program the independent
I²C buses in parallel. The stateless native C transactions release the Python
GIL. All worker updates finish before restoration on failure or interruption.
Both clocks are compared directly to PS FCLK. External reference, absolute
phase calibration and phase-noise qualification remain separate work.

The native backend can time line states using `probe_counter` at SYS = 100 MHz:
at least 150 ticks (1.5 µs), with unsigned wrap handling. It retains the CPU-timed
ABI for older bundles or different SYS frequencies. SCL stretch and a stalled
PL timer have bounded timeouts; both open-drain lines are released on failure.
NACK, invalid offsets and both timeout paths are covered with simulated-MMIO
software tests. Both PI controllers use Kp = 0.15 ppm/ns and
Ki = 0.30 ppm/(ns·s), with separate integrators and the same qualification limits.

Cyclic garbage collection is disabled only while a bounded phase-control
segment runs; normal reference counting continues, and the original GC policy
is restored afterward, including on exceptions. Long shared control gaps appeared while cyclic collection was enabled.
Generation-2 scans of retained phase history were identified as a likely cause. A full
scan of a completed two-card trace measured approximately 140 ms on Cortex-A9.
Collection runs between segments. Worker failures are joined before either
oscillator is restored, and this ordering and GC cleanup have software tests.

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
**Simultaneous dual-loop qualification passed.** Three 60-second runs covered
initial hold, reacquisition after isolated FMC1 loss, and reacquisition after
isolated FMC2 loss. Every final 20-second window passed the same prototype
criteria. The other detector remained valid and continued producing tags during
each isolated loss. Both initial Si570 RFREQ settings were read back after
restoration. The bounded test leaves no background servo.

| Final 20-second window | FMC1 phase stddev | FMC2 phase stddev | Worst absolute phase | Lock fraction, both |
|---|---:|---:|---:|---:|
| Initial, both controlled | 2.222 ns | 2.214 ns | 8.413 ns | 100% |
| After isolated FMC1 loss | 1.983 ns | 1.976 ns | 6.984 ns | 100% |
| After isolated FMC2 loss | 2.118 ns | 2.112 ns | 7.302 ns | 100% |

Median control intervals were approximately 5.29 ms for both cards. Maximum
intervals in the evaluation windows were below 7.85 ms; the earlier shared
61 ms gap did not recur. Both clocks passed simultaneous reciprocal checks,
including the exact 1:1 reference self-check. The final
[hardware validation](../evidence/zc706/wr-pll-dual-20261011/hardware-validation.json)
records every phase/frequency statistic, clock-loss state and tested file hash;
compressed full traces and failed development attempts are retained alongside it.
The bitstream SHA-256 is
`5b937de507bf32e884003baa60d7c2232dca43c4876909810a47649a784b9c2d`.

Use `make wr-pll-dual-package` to bundle the matched bitstream, CSR map, native
ARM backend, both regulator scripts, original WR VHDL, licenses and evidence.
Packaging requires a successful simultaneous two-card physical qualification
and rejects changed tested files. The original single-loop release remains
available; reproduce that exact bundle from its tagged source revision.

DCO÷4 phase hold establishes a common frequency and monitored phase reference.
ADC framing, cable/PCB delay calibration and physical simultaneous sample-phase
validation remain pending when the clock logic is integrated with acquisition.
