# ZC706 integrated NetworkReset + queue2 PL bundle

This is a qualified **PL diagnostic bundle, not an SD image**. Linux boots
from the existing ZC706 SD installation; JTAG loads PL temporarily. SD, QSPI,
boot environment and qualified older bundles remain unchanged.

Physical ZC706 rev1.2, XC7Z045FFG900-2, both FMC ADC100M4cha cards, independent
ADC clocks. Linux PS7 GP1 accesses the1-GiB PL SODIMM. Both ADC streams use
independent CDC FIFOs and separate buffers. Both WR PLLs run during capture.
The SFP path contains upstream LiteEth UDP/IP/MAC/PCS/GTX. NetworkReset gives
both FIFO endpoints and protocol state coherent reset. A depth2 native-command
queue cuts distant DDR-ready feedback. PHY and network configuration derives
from the existing qualified project; no upstream checkout edits or Vivado build.

## Qualified results

Same bitstream SHA256:
`7bdc77eaf6176facf147f43d2c0ee2ed2833e5ea1057a644d2431be3e83ac831`.

- Setup/hold PASS; SYS91.70/83.33MHz, ADC153.96/100 and123.44/100MHz.
- Linux boot, DDR training and three whole1-GiB BIST passes PASS.
- Both ADCs: captures up to4,194,304 samples/card, zero drops/data errors,
  about800MB/s/card finite capture. Sequence and ADC pattern tests PASS.
- Both PLLs during capture:23,533 phase records/card, stddev1.576/1.569ns.
- External switch:20/20 qualification ICMP,350/350 byte-exact UDP1..1400bytes;
  zero new CRC/preamble/clock errors. External warmup recorded separately.
- Cold internal PMA and PCS each1000/1000 PASS including first frame,
  no warmup/burst, zero new MAC/clock/data errors.
- Golden restored and DDR3×1GiB rechecked after every physical run.

Evidence directories in `evidence/zc706`: `integrated-queue2-seed4-build-20261023`,
`integrated-queue2-hardware-20261023`, `integrated-queue2-cold-pma-20261023`,
`integrated-queue2-cold-pcs-20261023`. Raw PLL archive checksum is retained there.
Continuous streaming, active-transfer reset recovery and deterministic sample
alignment are not qualified. Header probes are omitted in this integrated bit.

## Rebuild

Prepare locked sources/tools/runtime using [the fixed-Yosys guide](zc706-integrated-fixed-yosys.md).
The two new options default off; this target explicitly enables them. Golden
preroute input must be copied to Dell because source sync excludes evidence.
Do not lower the83.33MHz requirement or accept failed timing.

On the shared build server, after source synchronization:

```
dell-build sync kasli-linux
dell-build run kasli-linux make ENV= integrated-network-reset-pl
```

Output: `build/zc706-integrated-network-reset-queue2-seed4-20261023/gateware`.
This uses fixed Yosys/openXC7, experimental SRL timing, router2/seed4, same DDR
serializer reset and existing clock preroutes. It does not require Vivado.

## Test and restore

Fetch build artifacts explicitly into a separate WORK_DIR and place the
qualified/rebuilt ARM `pl-ddr-test`, `adc-ddr-read`, `i2c.so` there. Its structure
must include `gateware/csr.json` and `gateware/gateware/{top.bit,manifest.json,...}`.
Use actual management IP from UART/DHCP; last observed after validation192.168.2.20.
PL network IP is192.168.2.206, UDP1234; generator input is not needed for pattern tests.

```
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir WORK_DIR --output UNIQUE_OUTPUT --preflight-only
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir WORK_DIR --output UNIQUE_OUTPUT --external-network --program
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir WORK_DIR --output OTHER_OUTPUT --internal-loopback-only --program
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir WORK_DIR --output THIRD_OUTPUT --internal-loopback-only --internal-loopback-mode pcs --program
```

Wrapper acquires shared ZC706 lease before JTAG/reset/UART/network and holds it
through golden restoration/BIST. Do not run the unwrapped probe on a shared board.
No approval for persistent boot media writes is implied by temporary PL tests.

## Package

`tools/package_integrated.py` checks the exact tested bitstream, ARM/software
hashes and full core/restoration evidence. Optional repeated
`--loopback-validation` additionally verifies same-bit, restored, cold1000-frame
PMA/PCS results and exact counter deltas. Cold proof must not include warmup or
burst diagnostics. Package SHA256SUMS covers every included file; adjacent
`.tar.xz.sha256` covers the archive. Preserve all prior qualified bundles.
