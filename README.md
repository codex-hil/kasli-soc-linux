# Kasli-SoC Linux / LiteX / openXC7

Work in progress. **Kasli-SoC milestone 1 has not been validated on hardware.**
This repository is separate from upstream ARTIQ; the `upstream/` checkouts
remain unchanged.

**Physical ZC706 rev. 1.2:** BootROM → upstream U-Boot SPL → U-Boot →
openXC7 PL → Linux 6.18.40 / Buildroot boots from SD without JTAG or Vivado.
Linux runs on **both ARM Cortex-A9 cores** in SMP mode. UART, 1 Gb/s
Ethernet, DHCP and SSH work. AXI/CSR tests passed 10,036 reads/writes each
through `/dev/mem` and `/dev/uio0`; the counter runs at approximately
100 MHz. PS DDR passed `memtester 128M 3`, followed by another pass on the
final image. Full SD write/readback verification and the final test suite
passed. Physical Kasli-SoC validation remains pending.

## CERN FMC ADC on ZC706

The **single-card J5 LPC target** provides four channels, an ISERDES
receiver, 1,024-sample snapshots, SPI/I²C and automated test-pattern checks.
Build it with:

```sh
make bootstrap BOARD=zc706
make adc-test
make adc-pl
```

The card is installed in J5 LPC; VADJ was measured at 2.5 V. Physical tests
confirmed clock/frame reception, ADC SPI, and SI570/multiplexer I²C.
With FPGA HR termination and individual-lane training, all 34 patterns
(139,264 channel values) and a 1,024-sample snapshot passed on hardware.
The internal offset DAC → ADC test passed on all four channels across
all three ranges (933,888 values).
[Offset results and plots](docs/zc706-adc-offset.md).
Full analog characterization remains pending. Both cards now also capture
into PL DDR: [validated independent-clock acquisition](docs/zc706-adc-ddr.md).
See [the target, CSR map and limitations](docs/zc706-fmc-adc.md) and
[DIFF_TERM mapping and physical A/B tests](docs/hr-diff-term.md).

The **dual-card target, J5 LPC + J4 HPC**, has independent clocks, CSR banks
and snapshots. Build it with `make adc-dual-package`. Build, timing and
simulations passed. **Both physical cards passed concurrent tests on
2026-10-09:** 278,528 pattern values and separate 1,024-sample snapshots
per channel. U-Boot loads the target from SD without JTAG. HPC also passed
an internal offset sweep across all three ranges (933,888 values).
Inter-card synchronization is deferred.
[Dual-card design and validation](docs/zc706-adc-dual.md).

An external AFG1062 1 MHz / 1 Vpp sine wave was captured on CH1 of both
FMC cards: [waveforms and results](docs/zc706-afg.md).
All range and termination control settings were checked; physical CH1
measurements are documented in [ADC controls and results](docs/zc706-adc-controls.md).
Ranges and offset adjustment work. Independent BNC impedance qualification
of all eight inputs remains pending. Both CH1 inputs are connected in
parallel to AFG CH1; the LPC load response is asymmetric and remains
under investigation. The linked detailed ADC documents are currently in Polish.

## Kasli-SoC hardware and golden references

The Migen platform, `migen/build/platforms/sinara/kasli_soc.py`, declares
**XC7Z030-FFG676-3**, with LEDs AF19/AF23 using LVCMOS25. Additional PS/DDR
pins are defined in `migen-axi/src/migen_axi/platforms/kasli_soc.py`.
The ARTIQ target is `artiq-zynq/src/gateware/kasli_soc.py`.

The physical board revision has not yet been established. Migen declares
speed grade -3, while the current schematic uses XC7Z030-2FFG676I.
Routing for -1 is conservative for either grade, but the fitted device
marking still needs confirmation.

PS initialization comes from **M-Labs zynq-rs SZL**, using the existing
hardware configuration:

* PS_CLK: 33,333,333 Hz, `libboard_zynq/src/clocks/source.rs`.
* ARM and IO PLL: 1 GHz, `szl/src/main.rs`.
* DDR3L: the golden code describes MT41K256M16HA-125:E, operates in
  **16-bit mode**, disables slices 2/3 and exposes **512 MiB** at
  533,333,333 Hz. See `libboard_zynq/src/ddr/{mod,regs}.rs`.
  SZL configures the controller, IOBs and calibration; those settings are
  retained. The schematic routes 32 data lines to two MT41K256M16TW-107:P
  devices (1 GiB physically), but Linux uses the conservative region
  exposed by the golden loader.
* UART1: 115200 8N1, TX MIO48 / RX MIO49, 1.8 V bank.
  See `libboard_zynq/src/uart/mod.rs` and `stdio.rs`.
  PL serial pins Y18/AA18 are a separate interface.
* SD0: MIO40–45, card detect MIO46, `libboard_zynq/src/sdio/mod.rs`.
* GEM0: RGMII MIO16–27, MDIO MIO52/53, PHY reset GPIO MIO47,
  `libboard_zynq/src/eth/mod.rs`. `Kasli-SOC_ETH_PHY.SchDoc` confirms
  Marvell 88E1512 and explicitly states **“PHY MDIO address is 0.”**
* Reset and level shifters: `slcr.rs::init_preload_fpga/init_postload_fpga`.
* QSPI: no QSPI NOR device was found in the inspected upstream schematic.
  SZL supports SD/JTAG boot; this project does not assume a QSPI bootloader.
* USB: the connector serves the FT4232H (JTAG/UART/I²C/POR). No ULPI PHY
  for the PS USB controller was found; PS USB remains disabled.
* GTX/SFP, RTIO clocks and EEM are unnecessary for the minimal PL design.

Source revisions are pinned in `sources.lock.json`. The project uses
[LiteX Zynq7000](https://github.com/enjoy-digital/litex/blob/master/litex/soc/cores/cpu/zynq7000/core.py)
and [openXC7](https://github.com/openXC7/toolchain-nix).

## Porting map

ARTIQ/Migen element | LiteX/openXC7 equivalent | Kasli-SoC status
---|---|---
Sinara platform/LED | Small local platform in `gateware/kasli_soc.py` | Elaboration works
zynq-rs SZL PS/DDR/MIO | Existing loader with added FCLK0 configuration | `make szl` PASS
Migen-AXI PS7 | Upstream LiteX Zynq7000 / native PS7 primitive | Synthesis works
ARTIQ AXI/CSR | GP0 → upstream AXI3/Wishbone bridge → LiteX CSR | PL built; hardware validation pending
Vivado place-and-route | Yosys → nextpnr openXC7 → FASM → X-Ray bitstream | Experimental build works
ARTIQ runtime | Upstream U-Boot → upstream Linux → Buildroot | SD image built
ARTIQ RTIO/DRTIO | Later proof of concept | Not started

## Kasli-SoC architecture and boot

PS7 GP0 → AXI3 → LiteX Wishbone → CSR; FCLK0 at 100 MHz drives `sys`.
The minimal design has a 32-bit scratch register and counter, signature
`0x4b534f43`, and LED AF19 driven by counter bit 25.
The full map is generated as `build/gateware/csr.json`:

Register | Address | Access
---|---|---
scratch | 0x40000800 | RW
counter | 0x40000804 | RO
signature | 0x40000808 | RO

Kasli-SoC boot flow: BootROM SD → SZL → PL → U-Boot → Linux/rootfs.
U-Boot remaps OCM to the top of the address space and exposes DDR from
address 0 (`arch/arm/mach-zynq/cpu.c::arch_cpu_init`). UART/SD retain SZL's
MIO configuration. U-Boot has no Zynq7000 pinctrl driver; Linux initializes
Ethernet MIO.

The shared DTS uses `zynq-7000.dtsi` from the pinned upstream sources.
For U-Boot, it comes from `dts/upstream`, because the older `arch/arm/dts`
file lacks a pinctrl node. SZL loads the payload at 0x00100000; U-Boot must
be linked for that address. SZL remains the DDR/MIO configuration reference.
A small patch enables FCLK0 using IO PLL / 10 / 1; Linux must keep it running.

Kasli-SoC SD programming and physical boot have not yet been performed.
No QSPI programming has been performed. Set boot-mode switches according
to the documentation for the physical board revision. Return to ARTIQ using
the original SD card/boot mode; existing artifacts are preserved.

## Build and repository layout

* `gateware/`: minimal platform and SoC using the LiteX API.
* `tools/pl_test.py`: hardware tests of patterns, walking ones, random
  writes, signature and counter frequency; restores the original scratch value.
* `tools/hardware_test.py`: ping, SSH, `memtester 128M 3`, PL checks and
  PS7 dump; records separate logs and requires UART/boot evidence before
  accepting a milestone.
* `tools/capture_uart.py`: captures a specified 115200-baud UART without
  transmitting characters.
* `tools/dump_ps7_state.py`: reads SLCR/DDRC through `/dev/mem`, emits JSON
  and compares dumps. It does not read FIFOs. An ARTIQ dump still needs
  JTAG transport or integration into ARTIQ.
* `upstream/`, `.venv/`, `build/`: ignored working directories.
* `evidence/`: build and hardware evidence, labeled by board and test.
  Build-only evidence does not establish physical-board operation.

From a clean checkout on an x86_64 Linux host with Docker, Python 3 and Git:

```sh
make image
```

This prepares pinned Debian with a dated APT snapshot, fetches sources
from `sources.lock.json`, verifies FPGA tool archive SHA-256 checksums,
installs local Python/Rust dependencies, builds PL, SZL, U-Boot, Linux and
rootfs, then assembles `build/buildroot/images/sdcard.img` and its manifest.
Individual stages are `make bootstrap`, `make pl`, `make test-pl`,
`make szl` and `make linux`.

All stages, including U-Boot, Linux 6.18.40, rootfs and image assembly,
passed; a complete `make image` exited with code 0. The image is
335,544,832 bytes. The container's writable `/usr` and `/var` reside in
`build/environment/` on the project volume, keeping dependency installation
off the host system partition. Local elaboration diagnostics are also
available with `.venv/bin/python gateware/kasli_soc.py`.

FPGA tools used in the initial experiment:

* openXC7 release 2026-10-03; nextpnr c68c1358; prjxray-db a90f27c1.
* OSS CAD Suite 2026-10-05; Yosys 0.69+190 / 0e8336b4e.
* SZL: Rust nightly-2026-03-25, rust-src and clang.

Builds and larger dependencies are stored on an additional volume because
the original host system partition had less than 1 GB free.

## Kasli-SoC validation status

Yosys CHECK reported zero problems. nextpnr achieved 143.84 MHz, passing
the 100 MHz target. `make test-pl` passed 1,000 AXI/CSR transactions with
delayed AW/W, B/R backpressure, ID checks, signature, scratch and counter
verification. This simulates the post-Yosys netlist with PS7 as a black box
whose ports are driven by the testbench; it does not test CPU, DDR, MIO or
the physical FPGA.

A 5.8 MiB bitstream was generated through fasm2frames + xc7frames2bit
without Vivado. The available database contains FBG676-1 rather than
FFG676-3, so routing uses conservative speed grade -1. Package mapping is
checked against official AMD pinouts; successful routing alone is not
hardware validation. New nextpnr uses `--device` and `-o xdc=... -o fasm=...`;
the pinned LiteX backend emits older arguments. `tools/build_pl.py` adapts
the CLI and has passed the complete build.

Once Linux is running on Kasli-SoC:

```sh
python3 /usr/bin/pl_test.py --csr-json /etc/litex/csr.json --iterations 10000
python3 /usr/bin/dump_ps7_state.py > /tmp/ps7-linux.json
```

SSH, DHCP, ping, DDR stability and the complete PS→PL test have not yet been
performed on Kasli-SoC. Attached USB adapters have not been identified as
Kasli-SoC; commands are not sent to unidentified devices.

Element | Kasli-SoC status
---|---
PS7 | Golden reference and SZL built; native PS7 synthesized
DDR | zynq-rs configuration identified; hardware untested
UART | UART1/MIO48–49 identified; hardware untested
SD | MBR/FAT/ext4 image built; physical boot untested
U-Boot | Build PASS; entry 0x00100000; physical boot untested
Linux | Upstream 6.18.40 built; physical boot untested
Ethernet | GEM0/88E1512/address 0/reset identified; hardware untested
SSH | Dropbear and public key in rootfs; physical connection untested
AXI PS→PL | PL build passed; hardware untested
LiteX CSR | Map generated; 1,000 simulated transactions PASS; hardware untested
Yosys | Synthesis PASS
nextpnr-xilinx | Routing/timing PASS; new CLI adapter works
openXC7 bitstream | Artifact built; package alias pinout verified; hardware untested
ARTIQ RTIO PoC | Waiting for milestone 1

## Kasli-SoC SD image and first connection

Image: `build/buildroot/images/sdcard.img`.
Payload checksums: `build/buildroot/images/manifest.json`; a recorded
manifest is also in `evidence/image-manifest.json`.
This bring-up image has not yet been validated on Kasli-SoC.

Partition 1 is 64 MiB FAT with BOOT.BIN, zImage, DTB and extlinux.conf.
Partition 2 is 256 MiB ext4. After identifying and unmounting the correct SD card:

```sh
# Replace the path with the actual card identifier, without a -partN suffix.
sudo dd if=build/buildroot/images/sdcard.img of=/dev/disk/by-id/YOUR_SD_CARD bs=4M conv=fsync status=progress
```

UART: 115200 8N1; console login `root` with an empty password in this PoC.
Ethernet uses DHCP. SSH uses keys; password authentication is disabled:

```sh
ssh -i build/ssh/id_ed25519 root@DHCP_ADDRESS
python3 tools/hardware_test.py --help
```

The private key stays in ignored `build/ssh`; bootstrap generates a new key
for a fresh checkout. Do not publish it with the image. Physical Kasli-SoC
tests still need to confirm boot, DDR, UART, networking and PS→PL.

Every `make image` checks the MBR, partition boundaries/non-overlap and
byte-for-byte agreement with boot.vfat/rootfs.ext4. Repeat the audit with:

```sh
python3 tools/check_sd_image.py build/buildroot/images/sdcard.img
```

## Reproducing the build from Git

All project inputs are tracked:

* `Makefile`, `tools/environment.py`, `tools/image.py`: environment and build.
* `sources.lock.json`: upstream URLs and exact commits.
* `toolchains.lock.json`: FPGA tool archives and verified SHA-256 checksums.
* `requirements.lock`: Python dependency versions.
* `gateware/`, `tests/`: LiteX PL and AXI netlist tests.
* `patches/`: golden SZL FCLK0 patch.
* `buildroot/`: Linux/U-Boot/rootfs configurations, DTS, overlay, boot and SD setup.

The host needs x86_64 Linux, user access to Docker, Git, Make, Python 3 and
tar. Reserve at least 30 GiB for checkout/build and provide network access.
There is no need to copy `.venv`, `upstream/`, `build/` or dependencies
from the development machine. `make image` fetches pinned sources and
generates the artifacts. A reference container package list is recorded in
`evidence/debian-packages.txt`; the dated APT snapshot is specified in
`tools/environment.py`.

```sh
git clone https://github.com/codex-hil/kasli-soc-linux.git kasli-soc-linux
cd kasli-soc-linux
make image
```

Images are not byte-identical between checkouts: generated SSH keys,
timestamps and filesystem identifiers may differ. Every build records its
own SHA-256 manifest. Private keys and built images are not committed.
The [repository](https://github.com/codex-hil/kasli-soc-linux) is public.

## ZC706 as the intermediate platform

The pinned LiteX-Boards sources provide `xilinx_zc706` for
**XC7Z045-FFG900-2**. The supplied openXC7 has both the exact FFG900-2 part
and XC7Z045 chipdb. Upstream Linux provides `zynq-zc706.dts`, 1 GiB of
memory and PHY address MDIO 7.

Initial SZL feasibility checks built successfully with
`--no-default-features --features target_zc706` and the existing FCLK0 patch.
Golden zynq-rs sets CPU to 800 MHz, PS_CLK to 33.333333 MHz and 32-bit DDR
to 666.666666 MHz. That DDR configuration later failed physical checks;
the working ZC706 target uses **upstream U-Boot SPL PS7 initialization at
533 MHz**. Kasli-SoC retains golden SZL/ARTIQ initialization.

The existing LiteX-Boards SoC target uses a soft CPU and PL DDR, so this
project supplies a minimal PS7/CSR target with LED G2/LVCMOS15, DTS and
ZC706 image configuration. Do not boot the Kasli image on ZC706: DDR and
PHY configurations differ. Initial Yosys/nextpnr/openXC7 PL achieved
133.30 MHz against the 100 MHz target; SZL and 1,000 simulated AXI/CSR
transactions also passed. See `evidence/zc706-feasibility.json`.
ZC706 is an intermediate platform; it does not satisfy the Kasli milestone.

### Building ZC706

```sh
make BOARD=zc706 image
```

Output: `build/zc706/buildroot/images/sdcard.img`.
Individual stages include `make BOARD=zc706 pl`, `make BOARD=zc706 test-pl`
and `make BOARD=zc706 linux`. ZC706 uses upstream U-Boot SPL `ps7_init`;
Kasli uses SZL. The default `make image` still builds Kasli.
Tools, fetched sources and the SSH key are shared; PL, loader, Buildroot
and image outputs have separate directories. The minimal CSR map and
hardware test are common to both targets.

LED G2/LVCMOS15 comes from the LiteX ZC706 platform; Y21 is absent from the
available openXC7 database. The ZC706 DTS is copied from pinned upstream
Linux, with the LiteX UIO/FCLK0 node added.

ZC706 bring-up:

* SD slot J30. UG954 table 1-2 specifies SD boot as SW11.1–5 =
  `0 0 1 1 0`; check switch markings on your physical board.
* UART: USB Mini-B J21/CP2103, UART1 MIO48/49, 115200 8N1.
* Ethernet: RJ45 P3 / Marvell 88E1116R.

Reference: [AMD UG954 v1.8, pp. 17 and 49–52](https://docs.amd.com/api/khub/documents/m4fPXowvxKd5JZRfe046WQ/content).
SD boot does not require QSPI writes.

The `linux` stage reproduces the selected board defconfig. After changing
kernel configuration in an existing Buildroot directory, also use
`linux-reconfigure` or a fresh build directory, following the normal
Buildroot workflow.

The ZC706 SD image is 335,544,832 bytes; BOOT.BIN and partitions passed
validation. Manifests are in `evidence/zc706/`; physical boot, DDR, network
and PS→PL evidence is in `evidence/zc706/hardware-rev12-20261007/`.

### USB access on the development host

The original ZC706 introduced a CP2103 UART and Digilent adapter
`210251841109`; rev. 1.2 uses JTAG serial `210251842914`.
An administrator can grant temporary ACL access to the selected board:

```sh
sudo python3 /home/codex-hil/kasli-soc-linux/tools/grant_zc706_usb_access.py --jtag-serial 210251842914
```

The script resolves current USB numbers through sysfs and leaves other
adapters unchanged. Reconnection may require granting access again.
JTAG IDCODE identified XC7Z045; both CPU cores respond through JTAG.

### Historical bring-up and revision comparison

The initial rev. 1.0 investigation on 2026-10-07 confirmed PS UART
transmission (`ZC706 UART TEST`) and upstream U-Boot SPL execution in OCM.
A 64 KiB OCM readback matched the uploaded image, but full U-Boot/Linux
console output was not obtained. Early debugger register reads were
inconsistent; a single DDR result did not establish a memory fault.
Evidence: `evidence/zc706/hardware-20261007/`.

An independent comparator used published
[PULP/HERO ZC706 images](https://pulp-platform.org/hero/doc/downloads/images/zc706/).
Its historical vendor-generated PL is separate from this project's openXC7
build. The reference image was written to a physical 32 GB card
(31,914,983,424 bytes), and full readback SHA-256 matched.
See `evidence/zc706/hardware-20261007/sd-write.json`.
QSPI was left unchanged.

To reproduce the reference image after preparing the ZC706 toolchain:

```sh
python3 tools/environment.py python3 tools/zc706_reference.py --image
```

Output: `build/zc706-vendor-baseline/sdcard.img`, with a 64 MiB FAT
partition containing `BOOT.bin`, `uImage`, `devicetree.dtb` and
`uramdisk.image.gz`. `configs/zc706-reference.json` pins every download's
SHA-256; changed files at the upstream `latest` URL stop reproduction.
The script creates an image file without writing a device.

On rev. 1.0, SD boot left UART silent, BootROM PC at `0xffffff28`,
`BOOT_MODE=5` and `REBOOT_STATUS=0x00401000`. Optional AMD XSDB/existing
hw_server confirmed these observations; AMD tools are not build dependencies.
FSBL/U-Boot JTAG loading also failed to produce a console.

With POWER GOOD lit, J7 open, and PS7 initialized by the published HERO
FSBL, rev. 1.0 DDR repeatedly lost bit 12:
`ffffffff → ffffefff`, `00001000 → 00000000`, `55555555 → 55554555`
at `01000000`, `01000040` and `11000000`. Identical OCM accesses at
`00020000` passed. U-Boot branch `eaffffeb` read back as `eaffefeb`;
stepping confirmed a wrong branch target and exception. This did not
settle whether the cause was a board fault or revision-specific initialization.
Logs: `ddr-bit12-patterns.log`, `ocm-ddr-control.log`, `branch-readback.log`.
Rev. 1.0 SD BootROM behavior and DDR remain unresolved.

The same reference card booted on **rev. 1.2**, running Linux
`4.9.0-xilinx-v2017.2`, BusyBox and UART console. JTAG IDCODE was
`0x23731093`, MCTRL `0x30800100`; adapter `210251842914`.
Ethernet negotiated 1000/Full; DHCP assigned `192.168.2.7`; ping and SSH
passed. The kernel reported 901,732 KiB RAM. `memtester 128M 3` subsequently
passed every pattern in all three loops. Logs are in `ddr-memtester.log`,
with raw-log SHA-256 in `status.json`. The reference system's SSH key was
added in RAM and disappears on reboot; its default login is documented in
the [HERO SDK README](https://github.com/pulp-platform/hero-sdk/blob/master/README.md).

See [silicon revisions, errata and the next controlled DDR experiment](evidence/zc706/silicon-revisions-20261007.md).
Rev. 1.0 results remain separate from the working rev. 1.2 platform.

### First physical openXC7 PL success

On the running HERO reference system, this project's `top.bit` was loaded
through `/dev/xdevcfg`, with verified transfer SHA-256 and PCAP DONE=1.
Linux clock control set FCLK0 to approximately 100 MHz.
PS → AXI → LiteX CSR passed: signature `4b534f43`, scratch read/write,
10,000 transactions, counter 99,990,601 Hz and scratch restoration.
The Yosys/nextpnr/openXC7 bitstream SHA-256 was
`e5a836508795b7bca585caee43ab4fe65b00ede398fbdc2d7d90468f861357d2`.
Logs: `openxc7-program.log`, `csr-smoke.log`, `pl-test.log`.

Reproduce on the legacy reference system with the project SSH key:

```sh
python3 tools/load_pl_xdevcfg.py 192.168.2.7
python3 tools/environment.py /work/build/zc706/buildroot/host/bin/arm-linux-gcc \
  -static -O2 -Wall -Wextra /work/tools/pl_test.c -o /work/build/pl-test
ssh -i build/ssh/id_ed25519 -o UserKnownHostsFile=build/ssh/known_hosts \
  root@192.168.2.7 'cat > /tmp/pl-test; chmod 755 /tmp/pl-test; /tmp/pl-test 10000' \
  < build/pl-test
```

`load_pl_xdevcfg.py` supports the legacy reference kernel and does not
write SD or QSPI. Rebooting the reference card restores HERO PL.
This hybrid bring-up was not completion of the Kasli-SoC milestone.

A PS7 dump of the reference system with this PL is saved as
`ps7-reference-openxc7.json`: 108 registers, UART_CLK_CTRL `00001402`,
FPGA0_CLK_CTRL `00200500`, FCLK0 100 MHz. Host-side SSH transport does not
require Python in the old rootfs:

```sh
python3 tools/dump_ps7_state.py --ssh-address 192.168.2.7 > ps7.json
```

The initial project SD image was then written from RAM to the unmounted
SC32G card, CID `035344534333324780d55bcc91012a00`. All 335,544,832 bytes
were read back and matched SHA-256
`c771c39018c5f32d16f8afb3e5bae3610fb36c1bc713c61dc5044fd4d44f8015`.
The HERO image and its reproduction script remain available on the host.

### Working upstream loader and Linux

The first project SD restart ran SZL, but PL programming ended in
`DoneTimeout`. The PL partition held correct PCAP data; JTAG DDR pattern
checks showed corruption with SZL's 667 MHz configuration. This was not
accepted as a bitstream failure or proof of rev. 1.2 hardware damage.

Upstream U-Boot SPL uses the existing
`board/xilinx/zynq/zynq-zc706/ps7_init_gpl.c`, configuring DDR at 533 MHz,
matching the working HERO reference. SPL and the project U-Boot were first
loaded with open-source OpenOCD; U-Boot then booted Linux 6.18.40 and
Buildroot from SD. UART, 1 GiB DDR, DHCP, ping and SSH worked.

The current ZC706 flow is:

BootROM → U-Boot SPL → `u-boot.img` → `boot.scr` → openXC7 `top.bit` → Linux/ext4.

`boot.cmd` is the reproducible boot-script source. BOOT.BIN contains only
upstream SPL; U-Boot loads `top.bit` before starting Linux. A PL load
failure stops the boot script. The complete SPL-based
`make BOARD=zc706 image` exited with code 0. Current payload checksums are
in `evidence/zc706/image-manifest.json`.

The image also includes `rootfs.cpio.gz` for RAM-root recovery.
`tools/boot_zc706_uart.py --ram-root` intercepts autoboot and selects this
mode without saving U-Boot environment. It requires host Python with
`pyserial==3.5`, an explicit UART path and the working board's SSH address:

```sh
.venv/bin/python tools/boot_zc706_uart.py \
  --port /dev/serial/by-id/usb-Silicon_Labs_CP2103_USB_to_UART_Bridge_Controller_0001-if00-port0 \
  --reboot-ssh-address IP_ADDRESS --ram-root --output build/hardware/ram-boot
```

After confirming RAM rootfs, write the image over LAN:

```sh
python3 tools/write_sd_over_ssh.py IP_ADDRESS \
  --cid 035344534333324780d55bcc91012a00 \
  --image build/zc706/buildroot/images/sdcard.img \
  --output build/hardware/sd-write.json
```

That CID identifies the supplied SC32G card; use the actual CID for any
other card. The script refuses writes unless rootfs is in RAM and SD is
unmounted, checks CID/capacity, then compares full readback SHA-256 with
the image. Refusal with SD rootfs was physically tested. QSPI is unused.
The PL test supports both `--device /dev/uio0` and `/dev/mem`.

The validated final image SHA-256 is
`729c58c976ce71c6171a5a6e20f8d827a000702b7edc2853ad219f25d076d7de`.
It was fully written from recovery RAM; all 335,544,832 bytes were read back
and the hash matched. The SD image then booted SPL, U-Boot, PL, Linux,
console and ext4 rootfs; DHCP, ping with zero packet loss, and SSH passed.

SSH host keys are retrieved through the physical UART into the project's
`build/ssh/known_hosts`; a fresh rootfs/recovery may generate a new host
key. SSH host-key checks remain enabled. U-Boot uses a random MAC with its
RAM environment. On DHCP acquisition/renewal, the BusyBox hook sends
gratuitous ARP to refresh host/router entries. The environment is not
written to QSPI.

Run the full automated hardware test:

```sh
python3 tools/hardware_test.py IP_ADDRESS --output build/hardware/validation
```

The default is `memtester 128M 3`; `--ddr-loops 1` shortens a later boot
check. After three passing loops, one additional loop was run on the final
image, followed by UIO and a PS7 dump. Final results are recorded separately
and do not replace earlier logs.

### Current ZC706 rev. 1.2 status — PASS

Element | Status
---|---
PS7 | PASS, upstream U-Boot SPL ZC706 with existing ps7_init
DDR | PASS, 1 GiB / 533 MHz; `memtester 128M 3` on project Linux, no errors
UART | PASS, 115200 8N1
SD | PASS, full image write/readback SHA-256 match; boot without JTAG
U-Boot | PASS, SPL and main 2026.10-rc5; full UART log
Linux | PASS, upstream 6.18.40 / Buildroot from SD; both Cortex-A9 cores online
Ethernet | PASS, 1000/Full, DHCP and ping
SSH | PASS, project key
AXI PS→PL | PASS on physical hardware
LiteX CSR | PASS, 10,036 reads/writes each through devmem and UIO; counter ~100 MHz
Yosys | PASS, used for the built and loaded PL
nextpnr-xilinx/openXC7 | PASS, place-and-route and timing
openXC7 bitstream | PASS, PCAP DONE and physical CSR tests
ARTIQ RTIO PoC | Not started

All checks in `evidence/zc706/hardware-rev12-20261007/final-validation/`
exited with code 0: ping (5/5, no loss), SSH, `memtester 128M 1`, UIO
(10,036 reads/writes, counter ~100 MHz) and PS7 register reads.
`validation.json` links these results to the boot log and full SD readback
hash. BootROM/SPL/U-Boot/PL/Linux work without JTAG loading.
Software restarts were confirmed; complete power removal was not tested
in that validation run. Rev. 1.0 remains a separate unresolved case.

[Validated SD image and checksums](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-poc-20261007).
`make BOARD=zc706 image` also produces `sdcard.img.gz` and `SHA256SUMS`.
The archive decompresses to the exact validated image.

Example SSH access using the address from the original validation run:

```sh
ssh -i build/ssh/id_ed25519 -o UserKnownHostsFile=build/ssh/known_hosts root@192.168.2.15
```

Use the board's current DHCP address; it may differ after a reboot.
ZC706 bring-up is complete. Kasli-SoC milestone 1 still requires physical
Kasli-SoC tests; the RTIO proof of concept has not started.

## FMC connectivity and independent PL SODIMM

[FMC connectivity audit for both ZC706 slots](evidence/zc706/fmc-adc-pin-audit-20261007.md).
DCO and all ADC data lanes share an HR bank in each slot. J5 LPC was used
for initial acquisition; both cards have since passed the tests described
above.

Independent PL SODIMM bring-up:
[architecture, build and current status](docs/zc706-pl-ddr.md).
Yosys, patched nextpnr routing/timing and openXC7 bitstream generation passed
at 333⅓ MHz DDR / 83⅓ MHz system / 50 MHz GP1 and BIST. The static ARM
diagnostic and simulations (including clock crossings, injected errors,
byte lanes and synthesized GP0 CSRs) passed.

`make ddr-package` reproduces the bring-up bundle. Physical JTAG
programming, eight-lane DDR leveling, GP1 address checks and three full
1 GiB BIST passes passed on rev. 1.2 with zero errors:
[hardware evidence](evidence/zc706/pl-ddr-20261008/validation.json).
The standalone DDR target remains available; the combined target below adds
ADC acquisition. Its original validation left SD/QSPI unchanged.
DCI termination is not supported by the current backend; long-term
signal-integrity qualification remains pending.

## ADC capture into PL DDR — physically validated

The combined target retains both independent ADC clocks. Each card packs
its four-channel 64-bit sample ticks into 512-bit words, crosses into the
DDR domain through its own asynchronous FIFO, and writes a separate buffer
through a LiteDRAM DMA writer. Captures are finite and loss-detecting;
this target does not synchronize the two cards or continuously stream to Linux.

```sh
make adc-ddr-test
make adc-ddr-pl
make adc-ddr-software
make adc-ddr-axi-test
python3 tools/test_adc_ddr_hardware.py --host BOARD_IP --program --full-bist --analog
```

[Architecture, build and validation details](docs/zc706-adc-ddr.md).
**ZC706 rev. 1.2, 2026-10-09: PASS.** Both cards capture all eight channels
at 100 MS/s into separate 32 MiB buffers: approximately 800 MB/s per card,
1.6 GB/s combined using 16-bit storage. Long captures have more than 99.5%
estimated overlap. Complete counter and real-ADC pattern readback has zero
errors or dropped samples; CH1 on each card also captures the AFG1062
1 MHz sine into DDR. All eight memory byte lanes train, and three full
1 GiB BIST passes have zero errors.

The build uses Yosys, nextpnr/openXC7 and audited database overlays without
Vivado. It reuses the physically validated DDR MMCM/BUFG placement. SD
loading preserves QSPI and persistent boot settings. This is finite buffered
acquisition with independent clocks and epochs; Linux reads completed buffers
through GP1. Output: `build/zc706-adc-ddr/`.
[Hardware evidence](evidence/zc706/adc-ddr-20261009/hardware-validation.json).
`make adc-ddr-package` reproduces the artifact bundle.
[Download the qualified bitstream/tools and complete sample buffers](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-adc-ddr-validated-20261009).
