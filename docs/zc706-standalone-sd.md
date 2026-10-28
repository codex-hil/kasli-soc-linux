# ZC706 integrated standalone SD image

The SD image packages the physically qualified openXC7 integrated PL with
Linux/U-Boot and automatic dual WR PLL control. Physical SD boot after PS system reset and automatic runtime are now PASS
(2026-10-27). Cold power removal remains NOT_RUN. Earlier JTAG service tests
are retained separately; the new proof loads PL from SD through U-Boot.

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

Current image: `/home/codex-hil/artifacts/zc706-integrated-standalone-sd-20261027-mode-fix/sdcard.img.gz`.
Its adjacent `manifest.json` includes the compressed and uncompressed SHA256.
Use a positively identified SD card in the Optiplex reader; preserve a backup
of the existing card or use a separate card. Do not overwrite a guessed disk.
SD Wire now exposes the card to the host only after the guarded shutdown/
HOST transition described below; do not switch a running rootfs to HOST.

After writing and readback verification, install SD on the powered-off ZC706,
boot with UART capture, and verify automatic PL/DDR/PLL startup, SSH and external
SFP packets. Do not use JTAG PL loading during the standalone boot qualification.
Keep the existing golden SD image/card and volatile JTAG restoration path.
QSPI and persistent U-Boot environment need no changes.

## Historical packaged result (2026-10-23; superseded)

Compressed image: 19,336,242 bytes, SHA256
`cda14308a4888730c7b7d74c496a677906e06a2a902964ddd139a5fcb8c03b0d`.
Uncompressed image SHA256:
`921d516751de261b32bdc9d68513b7a96f1260a1b4d67c7a5f2c2cafad3dba1a`.
Offline image and content audits PASS; BOOT.BIN matches the base SPL.
U-Boot is configured to load `boot.scr` from `mmc 0:1` automatically.
Evidence: `evidence/zc706/integrated-standalone-sd-20261023`.
Physical SD write/readback/standalone boot remain NOT_RUN until a card is
available in the host reader. Existing board SD/QSPI were not modified.

## Historical SD Wire inventory (2026-10-27; initial blockers resolved below)

Cached USB/sysfs identification under both the ZC706 shared lease and the
existing `hil-storage` serial lock found controller `DP04I33Y`, factory FT200X
`0403:6015`, and sibling USB2640 reader `0424:4050`, serial `000000264001`.
The card is 31,914,983,424 bytes and has two partitions. Its current whole-disk
by-id is `usb-Generic_Ultra_HS-SD_MMC_000000264001-0:0`.
This supersedes the earlier absence of a host-visible SD reader.

Current upstream `codex-hil/lab-instruments` support at
`c0ddc6b4f6b8a0176abd6abae8fb91b1dd4edb88` reports
`UNCOMMISSIONED_FACTORY`, ownership unknown and `supports_off=False`.
The legacy backend explicitly rejects switching/writing (`OFF_UNSUPPORTED`);
this project did not bypass it with raw block writes or direct FTDI commands.
No block content read, write, USB control request, EEPROM change, switch,
UART, reset or FPGA programming was performed during this inventory.

Before further hardware work, clarify physical SD Wire revision/target wiring
and qualify an appropriate backend/ownership path. The 2026-10-25 workspace
instructions also identify CP2103 USB1-1.3/serial0001 as FIT PM12, conflicting
with this project's historical ZC706 UART path. Do not open that UART or reset
the board using the old wrapper until its current assignment is resolved.
Evidence: `evidence/zc706/sdwire-inventory-20261027/report.json`.

## Physical standalone SD qualification (2026-10-27)

SD Wire v1.4 controller DP04I33Y was factory-configured with CBUS0 AWAKE21.
The owner authorized controller/library repair. Original EEPROM was backed
up privately; only CBUS0 and the two checksum bytes changed, preserving USB
identity. A controller USB reset activated IOMODE8. Guarded HOST/DUT/HOST,
full image write and readback physically PASS. Support and bounded board
wrappers are in [lab-instruments](https://github.com/codex-hil/lab-instruments/blob/main/docs/sdwire-guarded.md),
commit42cf1b7. The original isolated-storage CLI remains read-only; use the
new guarded workflow with actual DUT stop readback.

The first SD boot exposed an image-packaging defect: the staged ARM tools
had mode0600. Manual chmod demonstrated the fix; the packager now installs
ARM executables as0755 and the offline checker verifies their root ownership
and mode. The first image and failure evidence remain intact.

The corrected image was rebuilt on Dell, audited, separately written and
fully read back, and booted without JTAG PL loading or manual service commands.
UART records SPL, U-Boot, a13,321,505-byte PL load from SD, Linux and login.
SSH/DHCP192.168.2.21 PASS. Automatic service passed DDR init/leveling and
three whole-1-GiB BIST passes, initialized/calibrated both ADC receivers and
ran both WR-derived PLLs. Both `locked` statuses remained true over42.19s of
sampled observation and after external SFP traffic:20/20 ICMP,350/350 exact
UDP, zero new CRC/preamble/clock errors. This run did not capture new ADC
sample data or qualify continuous streaming/jitter/deterministic alignment.

Compressed corrected image:19,335,976 bytes, SHA256
`5ca30585d6d4c92e1534592fc43bab919ad67b58e7dbc51fd67508650230680d`.
Expanded image:335,544,832 bytes, SHA256
`effe3ec9a450952cb57d917b790245bdf81025b7440ad823d9df951aae5305b8`.
Build-time manifest retains its original unvalidated status; the separate
`hardware-validation.json` joins the physical proof by exact image hash.
Evidence: `evidence/zc706/standalone-sd-hardware-20261027`.

All original partition extents and the complete overwritten range were
backed up (335,544,832 bytes, repeated-read SHA256 verified) to
`/srv/codex-hil-nvme/sdwire-backups/DP04I33Y/pre-integrated-20261027.img`.
This is not a full32-GB card backup; the remaining tail was not overwritten.
A second pre-update backup is retained alongside it. No QSPI or persistent
U-Boot environment write. Current UART CP2103 USB1-1.3 was positively confirmed
as ZC706 through hostname and correlated boot. Host access held the actual
ZC706/PM12 and storage leases; no other owner was preempted.

The board intentionally retains the corrected SD image and continuous dual
PLL service, with SD Wire on DUT. This authorized installation supersedes
restoring golden after temporary tests. Stop the service, sync/remount or
halt Linux and establish/read back the hardware stop guard before HOST
selection. An initial rootfs-shutdown recovery was not a clean shutdown;
the later healthy runtime completed rootfs read-only remount and kernel halt.
Cold power-cycle remains NOT_RUN: the qualified boot used PS system reset
through JTAG, with boot ROM and all payload loading from SD.


## Live-runtime soak follow-up

The unchanged SD runtime subsequently passed600.30s with4 finite dual ADC/DDR
batches,784.5MiB checked,28,000 exact UDP replies and80/80 ICMP. Both PLLs
were locked in195 fresh status observations; no service restart or new phase
rejections/MAC/clock errors. Original ADC fields restored with readback.
See [the soak scope and evidence](zc706-runtime-soak.md). Continuous streaming,
analog input qualification and cold power-cycle are not implied.

## Physical power-cycle follow-up — 2026-10-28

Owner reported removing/reapplying board power. Post-start validation PASS:
UART login, short uptime, SD ext4 rootfs, DHCP192.168.2.23 and strict-known-key
SSH. Initial SSH to former192.168.2.21 timed out; UART identified the new DHCP
lease without network or boot changes. Early SPL/U-Boot/BootROM UART output
was not captured and supply-off duration was not instrumented.

The automatic service initialized all DDR lanes and passed three whole1GiB
BISTs. Both PLLs remained locked in sampled status over41.37s. SFP passed
350 exact UDP replies and20/20 ICMP with zero new CRC/preamble/clock errors.
Four subsequent dual captures (8192/262144 sequence,262144 real ADC digital
pattern,262144 sequence) passed exact readback, zero drops. ADC SSR/control/
registers3+4/DMA configuration restored and service retained running PID118.
No analog input acquisition was performed in this follow-up.

Kernel reported ext4 journal recovery after the unclean power removal;
recovery completed and rootfs mounted read/write. This does not replace
an offline filesystem consistency scan or qualify repeated power-loss endurance.
No JTAG programming/reset, SD Wire switching or media rewrite was used.
All shared leases released.
[Evidence](../evidence/zc706/cold-sd-start-20261028/result.json).
