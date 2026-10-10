064-gtx-channel-conf currently never exercises or tags the GTX fabric-reference input. As a result, its generated database cannot describe the enable required by an open-flow GTGREFCLK design.

This change randomizes a nonconstant GTGREFCLK driver independently of the channel attribute/inversion tags, holds CPLLREFCLKSEL at 7, records GTGREFCLK_USED, and permits the test-only REQP-52 DRC for this mapping fuzzer. Unused channels and legacy parameter files tag the input as unused. Two regression tests cover generated connections, tag collection, both randomized states, unused channels and legacy input. No generated database files are modified.

Validation:

- All four Python tests in tests/ pass (two existing and two new).
- Controlled Vivado 2025.2 XC7Z030 model: comparing fabric versus dedicated reference adds channel-relative 31_09, 31_10, 31_54. A second comparison holds CPLLREFCLKSEL=7 and GTREFCLK1 fixed and changes only GTGREFCLK from PS FCLK to constant zero; the same three bits differ.
- Physical ZC706 rev. 1.2 / XC7Z045FFG900-2: the otherwise identical routed open-source design without additional bits has CPLLREFCLKLOST and fails loopback. Bit 31_10 alone also fails. Bit 31_54 alone restores the reference and passes 1000/1000 complete PCS/MAC PMA loopback frames with zero errors and 125 MHz TX/RX clocks; adding all three bits also passes 1000 frames.
- An integrated Yosys/nextpnr/openXC7 build using the measured minimal 31_54 overlay feature independently passes 1000 frames, without manual frame edits. Vendor/model bitstreams were never programmed on the hardware.

The new tag records the vendor connection-use pattern, which can include gates beyond the minimal physically necessary subset. The full randomized fuzzer has NOT been rerun under its supported Vivado 2017.2; 2025.2 was used only for controlled models. No mapping of MID_LEFT/MID_RIGHT or other families is inferred from this physical test. GTGREFCLK is a test-only clock, so this is not a low-jitter reference qualification. Dedicated Si5324 cross-quad routing remains open. SFP EEPROM returned NACK and external switch traffic was NOT_RUN.

[Port-only comparator evidence](https://github.com/codex-hil/kasli-soc-linux/blob/main/evidence/zc706/sfp-20261010/vivado-fabric-refclk-port-only.json), [physical isolation](https://github.com/codex-hil/kasli-soc-linux/tree/main/evidence/zc706/sfp-20261010/fclk-bit-isolation), [integrated qualification](https://github.com/codex-hil/kasli-soc-linux/tree/main/evidence/zc706/sfp-20261010/fclk-integrated), [reproducer and limitations](https://github.com/codex-hil/kasli-soc-linux/blob/main/docs/zc706-sfp.md). [Companion nextpnr PR #83](https://github.com/openXC7/nextpnr/pull/83) preserves the reference nets and emits the enable feature. No direct PR is sent to prjxray-db, following its contribution policy.

Signed-off-by: Greg Kasprowicz <gkasprow@gmail.com>, added on his explicit instruction. The implementation and evidence were prepared with OpenAI Codex assistance and tested as described above.
