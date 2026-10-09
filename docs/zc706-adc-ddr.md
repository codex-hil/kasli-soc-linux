# Independent-clock FMC ADC acquisition into PL DDR

Implementation and validation in progress. The existing standalone ADC and
PL DDR targets remain available and unchanged in their hardware interfaces.
The combined target is `gateware/zc706_adc_ddr.py`.

## Architecture

Each FMC has its own Si570, DCO, recovered 100 MHz ADC clock, receiver,
packer, asynchronous FIFO and LiteDRAM DMA writer:

```text
LPC: 4 × 16 bits @ adc  ── 8-tick packer ── async FIFO ── DMA writer ─┐
                                                                  ├─ LiteDRAM ─ PL SODIMM
HPC: 4 × 16 bits @ adc2 ── 8-tick packer ── async FIFO ── DMA writer ─┘
                                                                    ↑
Linux / GP0: control, training and capture status                     │
Linux / GP1: uncached readout of completed buffers ───────────────────┘
```

ADC clocks are independent; there is no assumption that their frequency or
phase agrees with each other or the 83⅓ MHz memory-controller clock.
Eight chronological four-channel sample ticks form one 512-bit native DDR
word. The earliest tick occupies bits 0..63. Each tick contains CH1..CH4
as four little-endian 16-bit words, with signed 14-bit ADC data left-aligned.
The 256-word FIFO per card stores 16 KiB, approximately 20.48 µs at nominal
100 MS/s. Each writer uses an additional 16-word buffered native FIFO.
A registered valid/ready buffer separates each FIFO from DDR command
backpressure. The common FIFO reset is upstream LiteX `ClockDomainCrossing` with
`with_common_rst=True`, so resetting an ADC receiver also resets both
sides of that card's FIFO.

The existing DDR PHY, training software, 333⅓ MHz DDR clock and 64-bit
1 GiB SODIMM are reused. PS Linux RAM is separate. GP1 maps PL RAM at
`0x80000000..0xbfffffff`; GP0 maps CSRs at `0x40000000`.
Default test buffers begin at PL RAM byte offsets `0x02000000` (LPC) and
`0x10000000` (HPC). They are not Linux physical addresses.

## Capture semantics and integrity

Captures are finite; length is a count of 64-bit sample ticks and must be a
nonzero multiple of eight. Base offsets must be 64-byte aligned, and the
entire buffer must fit in the SODIMM. Configuration is latched before a
request/acknowledgement handshake crosses into each ADC domain. The two
start commands do not define a shared acquisition epoch. Do not reset a
receiver or reinitialize DDR during an active capture.

An ADC cannot be backpressured. If a completed 512-bit block encounters a
full FIFO, that block is dropped, a sticky overflow flag is set, and its
eight sample ticks are counted as dropped. Such a capture fails validation;
loss is never reported as a successful continuous recording. Frame/alignment
failures also set a sticky flag. Captures drain before reporting completion.
`written` counts commands submitted to the native writer; completion also
waits for its write-data FIFO to drain. Native LiteDRAM has no persistent
media/commit acknowledgement. Software validates actual GP1 readback.

Status bits: 0 busy, 1 done, 2 FIFO overflow, 3 invalid ADC frame/alignment,
4 invalid configuration. Successful completion is exactly `0x02`.
Other registers are `base`, `length`, `synthetic`, `start`, `written`,
`dropped`, `ticks` and signature `0x41444452`. `ticks` counts system-clock
cycles including launch and drain overhead. The generated `csr.json` is
the address-map reference; combined-target ADC banks differ from the
standalone snapshot target.

The optional sequence diagnostic replaces the receiver's sample payload
with `[sample_index, sample_index XOR (0xadc00000 + card)]`, still generated
on that card's recovered ADC clock. Every stored tick can then be checked
for loss, repetition, corruption, ordering or mixing cards. It tests the
packer/CDC/writer/DDR path, not analog conversion. Separate runs use real
LTC2174 asymmetric digital patterns through the receiver and memory path.

## Build

```sh
make BOARD=zc706 image
make adc-ddr-test
make adc-ddr-pl
make adc-ddr-software
```

The baseline image step also supplies the ARM cross-compiler and working
SD Linux. If it is already built, start with `make adc-ddr-test`.
Artifacts are in `build/zc706-adc-ddr/`. The flow uses snapshot Debian Yosys
0.52 with conventional ABC, the existing patched nextpnr with both HP DDR
and HR DIFF_TERM support, a composed HP-metadata/HR-package chipdb, and the
HR termination database overlay. The combined build enables nextpnr’s
existing `-o hold-fix=8` pass with `-o hold-buffer-radius=48`;
the isolated `nextpnr-hold-buffer-radius.patch` makes the search radius
configurable while retaining the upstream default of 12. It repairs short paths with routing detours
or identity LUTs and still rejects residual setup/hold violations.
The same patch restores Fmax and critical-path reporting during the final
hold-repair timing analysis; its original disabled Fmax reporting also
disabled the final setup check. Both checks remain enabled in this build.

Two missing `CLK_HROW_TOP_R` activation features, `CK_IN_L10_ACTIVE` and
`CK_IN_L11_ACTIVE`, are supplied by an isolated database overlay. Their
bit mappings agree in both pinned Artix-7 and Spartan-7 databases; all
2,582 shared features of this tile type agree with the pinned Zynq database.
`patches/prjxray-zynq-clock-inputs.json` records the source hashes and
exact mappings. The build checks this agreement before applying the overlay.
Original upstream checkouts and standalone
build artifacts are preserved. DDR pad connectivity and all 22 requested
FMC differential terminations must pass build audits.

## Hardware bring-up

Automated loading, training and complete readback validation:

```sh
python3 tools/test_adc_ddr_hardware.py --host BOARD_IP --program --full-bist --analog
```

`--analog` additionally connects CH1 at ±5 V with analog termination OFF
and captures the external signal after the pattern tests. It requires a
suitable source; this setup uses the existing AFG1062 1 MHz / 1 Vpp signal.
The other channels remain disconnected. To analyze the saved waveforms:

```sh
python3 tools/environment.py python3 tools/analyze_adc_ddr_sine.py PATH_TO_CAPTURE_DIRECTORY
```


Use the matched successful bitstream manifest. Load the combined bitstream
through the existing SD/U-Boot loader:

```sh
.venv/bin/python tools/boot_adc_jtag.py --sd --host BOARD_IP \
  --bit build/zc706-adc-ddr/gateware/gateware/top.bit \
  --output build/zc706-adc-ddr/hardware/boot
```

This stores a content-addressed file on the existing SD rootfs and changes
only this boot's PL load choice. Default boot files, persistent U-Boot
environment and QSPI remain unchanged. An ordinary default boot returns to
the standard probe target.

Upload `pl-ddr-test`, `adc-ddr-read`, `csr.json`, `fmc_adc.py` and
`capture_adc_ddr.py` to the board. Initialize and train DDR first:

```sh
/tmp/pl-ddr-test --init-only
python3 /tmp/capture_adc_ddr.py --csr-json /tmp/csr.json \
  --reader /tmp/adc-ddr-read --output /tmp/adc-ddr-validation
```

`--init-only` still performs upstream training, the CPU memory smoke test
and address-alias checks; it skips the three whole-capacity BIST passes.
Initialization overwrites PL RAM. The acquisition test trains both ADCs,
checks receiver patterns, captures both sequence streams at increasing
lengths, reads every sample, checks real ADC patterns, then repeats a long
sequence capture. A timeout with an active writer requires a whole-PL
reload; the script does not reset one side of an outstanding FIFO.

At 100 MS/s, each card produces 800 MB/s; both together produce 1.6 GB/s
(decimal), using 16-bit storage per channel. Physical sustained-rate
qualification requires overlapping long captures with no drops and exact
readback. This is buffered capture, not a continuous 1.6 GB/s Linux/network
stream. GP1 readout is much slower than native DDR writes.

## Timing investigation

The first combined routing was rejected: the system domain reached
81.43 MHz against an 83⅓ MHz requirement, and five ADC FIFO BRAM input
arcs had approximately −0.02 ns hold slack. The critical setup path ran
from the DDR bank-machine queue through native command-ready logic to
the asynchronous FIFO read address. A registered valid/ready buffer now
breaks that feedback path; the existing nextpnr hold-fix pass handles
short data paths. The rejected artifact was not programmed.

The next build passed setup (87.32 MHz before hold repair, 88.92 MHz
after its first repair pass), but three 0.02–0.03 ns hold violations remained:
the default 12-tile search required a completely empty tile and found none
near those BRAM inputs. The combined backend now searches up to 48 tiles
for a legal identity buffer. Residual violations still fail the build.

The completed combined build passes all eight reported clock constraints.
The system domain reaches 88.92 MHz against 83⅓ MHz, the two ADC sample
domains reach 151.26 and 156.64 MHz against 100 MHz, and both DCO domains
reach 589.97 MHz against 400 MHz. Four identity buffers repair the short
BRAM input paths, leaving zero hold violations. Bitstream assembly and
the 22 differential-termination audit pass without Vivado.
See [build evidence](../evidence/zc706/adc-ddr-20261009/build-validation.json).

## Status

Element | Status
---|---
Two independent ADC clocks | Retained from validated receivers
Packing and asynchronous FIFO CDC | Implemented; simulation PASS
Repeated captures and ADC reset | Simulation PASS
Backpressure and overflow detection | Simulation PASS
Real ADC payload and frame error checks | Simulation PASS
Combined openXC7 bitstream | PASS: setup, hold, bitstream and 22 terminations
DDR training with both FMC receivers present | Hardware pending
Concurrent full-rate capture and exact DDR readback | Hardware pending
Analog acquisition into DDR | Not yet tested
Inter-card synchronization | Deferred
