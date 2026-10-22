# Qualified ZC706 integrated fixed-Yosys build

Physical qualification 2026-10-22: ZC706 rev1.2, XC7Z045FFG900-2,
two FMC ADC100M4cha v6.1, independent100MHz ADC clocks, PL SODIMM,
WR-derived dual PLL and external FS SFP-GE-T through the Netgear switch.
This is a PL diagnostic bundle, **not an SD image**. Existing SD Linux boots
both Cortex-A9 cores. Kasli-SoC hardware qualification remains pending.

Bitstream SHA256:
`3d050ef1cb859bb494df726d328a75059423bdb792f519036ecae533feccde6e`.

## Results and limits

- SYS85.11/83.333MHz, ADC1 120.35/100MHz, ADC2 103.80/100MHz; setup/hold PASS.
- All35 static SRL16E covered by experimental SDF-derived timing model.
- DDR init/leveling, GP1 address test and three whole1GiB BIST passes PASS.
- Dual independent ADC sequence/pattern/rearm,4194304samples/card, no errors/drops.
- Concurrent dual PLL:21787phase records/card,std1.712/1.704ns.
- External switch:20/20ICMP,350/350byte-exactUDP,157300bytes; no new MAC/clock errors.
- Golden restored and three whole1GiB BIST passes PASS, final DHCP192.168.2.18.
- Internal PMA loopback NOT_RUN. Continuous streaming and deterministic sample
  alignment are not qualified. No SD/QSPI/OTP writes were performed.

## Build

Use the repository environment and pinned `sources.lock.json` and
`toolchains.lock.json`. This qualification used the installed/cached environment,
not a clean cache-free replay. No Vivado was used. Yosys from pinned OSS CAD
Suite20261005 is0.69+190 (`0e8336b4e`); the older0.52 drops SRL clock enables.

On the shared build host, following `docs/toolchains/heavy-builds-remote-handoff.md`
in the parent workspace:

```sh
dell-build sync kasli-linux
dell-build run kasli-linux timeout 3600 build/python/bin/python tools/build_pl.py \
  --board zc706 --design integrated --ddr-sync-reset --no-header-probes \
  --srl-timing --seed 3 --router router2 \
  --prerouted evidence/zc706/integrated-20261013/golden-mmcm-native-prerouted.txt \
  --output-dir build/zc706-integrated-yosys-fixed-cdc-ready/gateware \
  --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys
```

The integrated backend composes existing clock/hold fixes and isolated static
SRL timing. Alias-only techmap preserves DDR inouts. ADC CDC/output/command
queues, registered-ready cut, buffered bank commands, and a scoped optional
AXI beat pipeline close the observed paths. The LiteX checkout stays unchanged:
`gateware/axi_beat_pipeline.py` applies the pinned patch to a temporary module.
Its11 upstream AXI regressions and dual-clock ADC simulation passed.

## Physical test

Keep the documented shared board lease across programming, UART, SSH, tests
and restoration. Use the wrapper; do not run child hardware tools separately.
Actual management DHCP may change on reset.

```sh
python3 tools/test_integrated_hardware.py \
  --host ACTUAL_IP --work-dir build/zc706-integrated-yosys-fixed-cdc-ready \
  --output /tmp/zc706-cdc-ready-hardware --program --external-network
```

Qualified `pl-ddr-test`, `adc-ddr-read`, `i2c.so` match236CSR registers,
memory maps and existing constants. Only `axi_beat_buffered=1` is added.
Hashes are retained in the physical validation evidence. Evidence is under
`evidence/zc706/integrated-fixed-cdc-20261022`.

## Package

```sh
python3 tools/package_integrated.py \
  --work-dir build/zc706-integrated-yosys-fixed-cdc-ready \
  --evidence-dir evidence/zc706/integrated-fixed-cdc-20261022 \
  --validation evidence/zc706/integrated-fixed-cdc-20261022/validation.json \
  --readme docs/zc706-integrated-fixed-yosys.md \
  --output /home/codex-hil/artifacts/zc706-fixed-cdc/zc706-integrated-fixed-yosys.tar.xz
```

The packager rejects mismatched bitstreams/software or absent core/restoration
proof and emits SHA256SUMS. Preserve the earlier qualified no-SRL bundle.
