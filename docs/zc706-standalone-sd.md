# ZC706 integrated standalone SD image

The SD image packages the physically qualified openXC7 integrated PL with
Linux/U-Boot and automatic dual WR PLL control. Physical standalone SD boot
has not yet been tested. The service was tested on ZC706 through the existing
JTAG boot wrapper; that is not proof of SD boot.

## Boot and runtime

BootROM loads SPL from `BOOT.BIN`; SPL loads `u-boot.img`. U-Boot executes
`boot.scr`, loads `top.bit` from FAT, applies the same PS clock/reset sequence
as the qualified JTAG path, then boots Linux with the ext4 root partition.
The baseline SD image and original build outputs are preserved separately.

`/etc/init.d/S99integrated start` runs `/opt/zc706-integrated/integrated_service.py`:

1. Verify runtime files and the installed CSR map against their manifest.
2. Initialize/level PL DDR and run three whole-1-GiB BIST passes.
3. Initialize the SFP reference clock and external Ethernet path.
4. Initialize and calibrate both independent ADC receivers.
5. Acquire both Si570 oscillators and run the existing WR-derived PI loops.

Status: `/run/zc706-integrated/pll.status.json`. Startup log:
`/run/zc706-integrated/service.log`. Each PLL retains at most about 4,146
recent records (trimmed to 4,096 every 50 updates); frequency history is also
bounded. There is no lifetime trace or periodic control log on SD.
Status `running` alone is not a lock assertion; inspect both cards' `last.locked`
and `last.phase.phase_ns` fields. Physical service testing observed both cards
locked for 40 seconds, bounded 4,096-record windows and successful SIGTERM
restoration. This is not long-duration PLL qualification.

Use `/etc/init.d/S99integrated stop` before any ADC/clock diagnostic or FPGA
programming. Stopping restores the saved Si570 settings and resets phase
detectors. No automatic restart after a hardware/control error. The board-side
service lock supplements the host shared board lease; host tools still need
the canonical ZC706 lock for UART/JTAG/network/SPI and restoration.

## Build

Run heavy work on Dell using the existing `dell-build` profile. Prepare the
base ZC706 Buildroot output with `tools/image.py linux --board zc706` and
`tools/image.py image --board zc706` as documented in the main README. Prepare
a qualified work directory with the integrated PL, matching CSR and ARM tools,
plus a passing full-integration `validation.json`.

```
dell-build sync kasli-linux
dell-build run kasli-linux python3 tools/build_integrated_sd.py \
  --work-dir build/zc706-standalone-input-20261023 \
  --validation build/zc706-standalone-input-20261023/validation.json \
  --output build/zc706-integrated-standalone-sd-20261023
```

The packager reuses the base `rootfs.tar`, kernel, DTB, SPL and U-Boot;
this is packaging existing compiled outputs, not a fresh compiler/rootfs
rebuild. It does not modify the baseline Buildroot target/images. It runs
under Buildroot fakeroot to preserve root ownership in the new filesystem.
Choose a new output path for each attempt; existing output is never deleted.
Private SSH keys are not copied into the image; the base rootfs contains
the authorized public key, and the corresponding private key stays on the host.

```
dell-build run kasli-linux python3 tools/check_integrated_sd.py \
  --images build/zc706-integrated-standalone-sd-20261023/images \
  --host build/zc706/buildroot/host \
  --output build/zc706-integrated-standalone-sd-20261023/offline-check.json
```

The audit checks MBR/partition boundaries, every image checksum, actual FAT
boot payloads, runtime/CSR bytes extracted from ext4, and root-owned executable
init script. This remains an offline check, not physical boot validation.

## Physical installation and recovery

Current image: `/home/codex-hil/artifacts/zc706-integrated-standalone-sd-20261023/sdcard.img.gz`.
Its adjacent `manifest.json` includes the compressed and uncompressed SHA256.
Use a positively identified SD card in the Optiplex reader; preserve a backup
of the existing card or use a separate card. Do not overwrite a guessed disk.
The board's currently inserted card is not exposed as an Optiplex block device.

After writing and readback verification, install SD on the powered-off ZC706,
boot with UART capture, and verify automatic PL/DDR/PLL startup, SSH and external
SFP packets. Do not use JTAG PL loading during the standalone boot qualification.
Keep the existing golden SD image/card and volatile JTAG restoration path.
QSPI and persistent U-Boot environment need no changes.

## Packaged result (2026-10-23)

Compressed image: 19,336,242 bytes, SHA256
`cda14308a4888730c7b7d74c496a677906e06a2a902964ddd139a5fcb8c03b0d`.
Uncompressed image SHA256:
`921d516751de261b32bdc9d68513b7a96f1260a1b4d67c7a5f2c2cafad3dba1a`.
Offline image and content audits PASS; BOOT.BIN matches the base SPL.
U-Boot is configured to load `boot.scr` from `mmc 0:1` automatically.
Evidence: `evidence/zc706/integrated-standalone-sd-20261023`.
Physical SD write/readback/standalone boot remain NOT_RUN until a card is
available in the host reader. Existing board SD/QSPI were not modified.
