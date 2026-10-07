# ZC706 silicon revision investigation (2026-10-07)

PCB revisions are user-reported; silicon identification comes from recorded registers.

| Measurement | PCB rev. 1.0 | PCB rev. 1.2 |
|---|---|---|
| PL JTAG IDCODE | 0x03731093 (revision 0) | 0x23731093 (revision 2) |
| DEVCFG MCTRL | 0x10800000 (PS_VERSION 1) | 0x30800100 (PS_VERSION 3) |
| Interpretation | XC7Z045 engineering-sample silicon | XC7Z045 production silicon |

EN220 lists XC7Z045 CES with JTAG revision 0. EN229 also lists CES9925 with revision 0, so the exact CES suffix cannot be identified from these measurements alone. EN247 lists production XC7Z045 with revision 2 or later. This identifies our specimens, not every PCB of these revisions. No complete PCB schematic/BOM revision diff has been established.

Relevant CES differences in EN220:

- AR52021: slice 3 read-gate training result has invalid upper four bits; the workaround estimates them using the other slices. This is NOT documentation of data bit 12 stuck low. Our repeated bit-12 corruption remains unexplained.
- AR51907: SD BootROM uses 1-bit transfers at 400 kHz or below.
- AR52023: SD BootROM violates the required initial 74-clock interval. This makes card compatibility a plausible hypothesis for the separate SD boot failure, not a proven cause.
- AR52022: PS DAP system debug reset can hang the PS.
- AR52019: Ethernet TxDMA can hang.
- AR47578: PL readback via DevC is unavailable; this does not mean PL configuration is impossible.

Our current upstream U-Boot ZC706 ps7_init_gpl.c reads silicon version at runtime and selects distinct MIO, PLL, clock, DDR and peripheral initialization tables for PS versions 1, 2 and 3. Therefore the final SPL is a suitable next controlled experiment on the old board; success on production silicon does not validate the version-1 branch. Final SPL/533 MHz initialization has NOT yet been tested on our rev. 1.0 specimen. No hardware was reset or programmed for this investigation.

Next experiment: load the existing final SPL through JTAG into OCM on the old specimen, verify selected version-1 DDR initialization, then repeat walking-bit and address tests. Keep SD BootROM diagnosis separate, and do not write QSPI. If data corruption remains, compare DDR training registers and timings before concluding a physical DQ-path fault. Confirm exact CES suffix from package marking when accessible.

Primary sources:

- https://docs.amd.com/v/u/en-US/en220
- https://docs.amd.com/api/khub/documents/tQcjGEnskQ9yGvbbOKlxuw/content (EN229)
- https://docs.amd.com/api/khub/documents/nvT6Go3MRJkASZYoi2lamA/content (EN247)
- https://docs.amd.com/r/en-US/47916/Solution
- https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Device-Revisions
- upstream/u-boot/board/xilinx/zynq/zynq-zc706/ps7_init_gpl.c: ps7_init and ps7_post_config

Local observations: hardware-20261007/branch-readback.log and hardware-rev12-20261007/status.json.
