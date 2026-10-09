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
The common FIFO reset is upstream LiteX `ClockDomainCrossing` with
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
make bootstrap BOARD=zc706
make adc-ddr-test
make adc-ddr-pl
make adc-ddr-software
```

Artifacts are in `build/zc706-adc-ddr/`. The flow uses snapshot Debian Yosys
0.52 with conventional ABC, the existing patched nextpnr with both HP DDR
and HR DIFF_TERM support, a composed HP-metadata/HR-package chipdb, and the
HR termination database overlay. Original upstream checkouts and standalone
build artifacts are preserved. DDR pad connectivity and all 22 requested
FMC differential terminations must pass build audits.

## Hardware bring-up

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

## Status

Element | Status
---|---
Two independent ADC clocks | Retained from validated receivers
Packing and asynchronous FIFO CDC | Implemented; simulation PASS
Repeated captures and ADC reset | Simulation PASS
Backpressure and overflow detection | Simulation PASS
Real ADC payload and frame error checks | Simulation PASS
Combined openXC7 bitstream | Build in progress
DDR training with both FMC receivers present | Hardware pending
Concurrent full-rate capture and exact DDR readback | Hardware pending
Analog acquisition into DDR | Not yet tested
Inter-card synchronization | Deferred
