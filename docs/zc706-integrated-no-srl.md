# ZC706 integrated external Ethernet qualification

The 2026-10-21 tested image combines two independent FMC ADC100M4cha v6.1
streams, 1 GiB PL SODIMM, both WR-derived phase PLLs and external 1000BASE-X
Ethernet through an FS SFP-GE-T copper module and the Netgear switch.

Physical result: three full DDR BIST passes, exact captures up to 4,194,304
samples/card with both PLLs active, zero dropped samples, 20/20 measured ICMP
and 350/350 byte-exact UDP echoes. Settled network error deltas are zero.
Finite captures reach approximately 800 MB/s/card; continuous acquisition and
phase-coherent simultaneous sampling are not qualified.

SYS timing is 87.55 MHz versus 83.333 MHz required, hold clean. Bitstream SHA256:
`5be9d14ca583b9ad0740bac054362f2faa2c08d3d9074c6381850f12b4e6df6f`.
The build uses Yosys/openXC7, `-nosrl`, synchronous DDR reset and the recorded
golden MMCM routes. No Vivado is needed. SRL-on/off matched trials identify
an implementation-path failure; the exact faulty tool stage remains unresolved.

Near-end PMA loopback with the active copper module failed separately. The
external test does not claim that mode passed. A DAC is not qualified by these
RJ45 results. Golden ADC+DDR and original Si570 settings were restored; DDR
BIST passed again. No SD, QSPI, boot-environment, flash or OTP writes.

## Rebuild

Use the prepared remote environment described in
`/home/codex-hil/docs/toolchains/heavy-builds-remote-handoff.md`.
Source sync excludes evidence, so ensure the recorded prerouted file is also
present and matches its manifest hash. The migrated runtime/cache and nextpnr
Git metadata were checked; this run does not prove a clean, cache-free install.

```sh
dell-build sync kasli-linux
dell-build run kasli-linux timeout 2400 build/python/bin/python tools/build_pl.py \
  --board zc706 --design integrated --ddr-sync-reset --no-header-probes --no-srl \
  --seed 3 --router router2 \
  --prerouted evidence/zc706/integrated-20261013/golden-mmcm-native-prerouted.txt \
  --output-dir build/zc706-integrated-no-srl-span/gateware \
  --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys
dell-build fetch kasli-linux build/zc706-integrated-no-srl-span/gateware/ \
  build/zc706-integrated-no-srl-span/gateware/
```

Build software with `tools/build_ddr_software.py --output-dir` for this work
directory and the ARM compiler commands in `make integrated-software`, changing
the output directory. This physical trial reused qualified binaries after
checking all 126 ADC/DDR CSR entries, the memory map and ABI constants;
`no-srl-software-reuse.json` records their hashes.

## Test and package

On the local debug host, with the actual management IP:

```sh
.venv/bin/python tools/test_integrated_hardware.py \
  --host ACTUAL_IP --work-dir build/zc706-integrated-no-srl-span \
  --output build/FRESH_VALIDATION_DIRECTORY --program --external-network
python3 tools/package_integrated.py --work-dir build/zc706-integrated-no-srl-span \
  --evidence-dir evidence/zc706/integrated-20261021 --evidence-prefix no-srl \
  --readme docs/zc706-integrated-no-srl.md
```

The hardware wrapper owns the shared ZC706 lock across programming, UART,
network, clock tuning and restoration. Run it only with both FMCs and the
external RJ45 link connected. Concurrent DMA starts briefly use FIFO priority11;
PLL control uses priority10. The overlap criterion is measured and remains95%.
PLL PID ownership and original oscillator settings are journaled before tuning.

The archive is a PL/diagnostic bundle, **not an SD image**. Verify `SHA256SUMS`
after extraction. Physical evidence is under
`evidence/zc706/integrated-20261021/no-srl-*`; failed attempts and cleanup recovery
are recorded separately in the same directory. Existing older qualified
artifacts are retained.

## Fixed-Yosys SRL replacement candidate (2026-10-22)

The qualified no-SRL image above remains the baseline. Yosys0.69+190
(OSS CAD Suite20261005, commit0e8336b4e) fixes the enabled-FDRE SRL extraction
bug confirmed by the minimal, ARP and external SFP hardware tests.
The full integrated replacement is building; it is not hardware qualified.

`--srl-timing` now composes the experimental static SRL16E SDF model with
the integrated backend's clock routing and hold fixes. It builds an isolated
binary under `build/zc706-integrated-srl-timing/nextpnr`; the qualified binary
and tool defaults are preserved. Source/routed SRL counts, sequential endpoint
coverage and six-LUT placement remain mandatory before admission. SRLC32E,
dynamic taps and inverted SRL clocks are outside the model.

```sh
dell-build sync kasli-linux
dell-build run kasli-linux timeout 3600 build/python/bin/python tools/build_pl.py \
  --board zc706 --design integrated --ddr-sync-reset --no-header-probes \
  --srl-timing --seed 3 --router router2 \
  --prerouted evidence/zc706/integrated-20261013/golden-mmcm-native-prerouted.txt \
  --output-dir build/zc706-integrated-yosys-fixed/gateware \
  --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys
```

Next: fetch the completed build, inspect timing/coverage and DDR I/O,
verify software CSR compatibility, then run the bounded integrated external
network/dual-ADC/dual-PLL/DDR wrapper under the shared board lease, including
golden restoration and DDR BIST. Current management address after the last
restoration is192.168.2.10; DHCP may change on reset.

Candidate update: synthesis is currently rejected before routing because DDR
IOBUF pads lose top-level connectivity. Clock admission now follows actual
PS FCLK0→BUFG→GTX connections rather than a Yosys wire alias. Alias cleanup
removes155 `$buf` cells but does not restore the DDR pad connections; it is
not a qualified fix. All64 DQ pads remain connected after elaboration,
flattening, preparation and memory mapping. Later synthesis stages are under
investigation with `tools/probe_ddr_elaboration.py`. The minimal explicit IOBUF
passes five normalization/round-trip controls (`tools/test_yosys_inout.py`).
Evidence: `evidence/zc706/integrated-fixed-admission-20261022`.
No candidate hardware programming has occurred.

Further isolation: all64 DQ connections survive through `map_luts` and
finalization when checked from the mapped snapshot. Explicit `bufnorm -conn`
then disconnects64/64 pads, including `-flat` and top-only selection controls.
The added normalization cleanup has been removed. The DDR pad admission
continues to reject the bad result. A full uninterrupted synthesis without
normalization is being compared with the admitted staged snapshot; the
original155-buffer observation is not yet explained. This is an offline
Yosys investigation, not evidence of board damage or a qualified replacement.

Alias-removal update: full uninterrupted synthesis retains64/64 DQ connections
but155 `$buf` cells. `opt_clean`, `opt_expr` and buffer-mode reset leave them.
An explicit identity-only techmap (`gateware/yosys/alias_buffers.v`) removes
all155 without buffer-normalizing the design. DDR DQ/DQS connectivity and
structural SFP FCLK admission PASS;35 SRL16E remain. The build script now runs
that map and asserts no `$buf`/`$_BUF_` before JSON export. Full routing/timing
and hardware qualification are pending. Controls and hashes are recorded in
`cleanup-probe.json` and `alias-map-admission.json` in the admission evidence.
