A GTX channel driven by a fabric reference clock loses its reference in the current packer: the hardwired-clock filter also matches CPLLREFCLKSEL control pins and GTGREFCLK, disconnecting the selector constants and the routable clock input. Preserving the nets alone is insufficient because the GTX FASM writer does not emit the fabric-input enable.

This change retains selector and GTGREFCLK connections, records a nonconstant fabric input and emits GTGREFCLK_USED. It changes only the Xilinx packer/FASM writer, with a qualification note in the porting documentation. Dedicated north/south reference mux routing is outside this change.

Validation:

- Applied cleanly to current openXC7/nextpnr main at 8006fbc6. The rebased latest tree has not had a full compile/hardware rerun.
- The equivalent isolated patch compiled and passed routing setup/hold checks on pinned c68c1358, using Yosys, nextpnr and openXC7.
- Physical ZC706 rev. 1.2 / XC7Z045FFG900-2, PS FCLK 100 MHz: integrated automatic build passed 1000/1000 complete LiteEth PCS/MAC near-end PMA loopback frames, zero payload/CRC/preamble errors, TX/RX clocks about 125 MHz. Linux boot, UART and SSH passed. No manual frame edits in this integrated build.
- Controlled frame-only isolation on the same routed design: baseline loses reference and fails; bit 31_10 alone fails; bit 31_54 alone passes 16 frames and then 1000 frames. On the SFP channel this is frame 0x0046329f, word 58, bit 22.
- Vendor XC7Z030 model comparison, selector held at 7 and dedicated input unchanged, changing only GTGREFCLK connectivity: adds 31_09, 31_10, 31_54. Physical isolation shows only 31_54 is necessary in our design; the local database overlay uses that minimal feature. No vendor/model bitstream was programmed onto ZC706.

The companion [Project X-Ray PR #2576](https://github.com/f4pga/prjxray/pull/2576) records the input-use pattern; the database needs that feature before enabling this input in a normal upstream installation. Our reproducible Zynq GTX overlay is experimental and is not claimed to be complete ZC706 support. GTGREFCLK is a test-only reference; these tests do not qualify jitter or an external link. SFP EEPROM returned NACK, so switch ICMP/UDP tests were NOT_RUN. Si5324 cross-quad clock routing remains open.

[Reproducer and limitations](https://github.com/codex-hil/kasli-soc-linux/blob/main/docs/zc706-sfp.md), [physical isolation](https://github.com/codex-hil/kasli-soc-linux/tree/main/evidence/zc706/sfp-20261010/fclk-bit-isolation), [integrated qualification](https://github.com/codex-hil/kasli-soc-linux/tree/main/evidence/zc706/sfp-20261010/fclk-integrated), [ready bitstream and checksums](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-sfp-fclk-loopback-20261010).

Signed-off-by: Greg Kasprowicz <gkasprow@gmail.com>, added on his explicit instruction. The implementation and evidence were prepared with OpenAI Codex assistance and tested as described above.
