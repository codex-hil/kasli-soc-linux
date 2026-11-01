# Project handoff — 2026-11-01

## Decision and scope

**ZC706 proof of concept closed by the owner on 2026-10-28.** Do not restart
experiments merely because a supervisor resumes this thread. The owner currently
has ZC706 only; resume the Kasli-SoC port when that physical board is available.
The original physical Kasli-SoC milestone is **not achieved**. No hardware was
accessed while preparing this handoff. Last physical observations below are
from 2026-10-28, not current availability checks.

Repository: https://github.com/codex-hil/kasli-soc-linux
Supporting SD Wire library: https://github.com/codex-hil/lab-instruments

Validated source checkpoints:

- `9dbc57d`: ten-minute integrated runtime soak.
- `6efd9e1`: live analog CH1 acquisition on both FMCs.
- `27dfa83`: autonomous runtime after owner-reported physical power cycle.

## Hardware and architecture

ZC706 rev1.2, XC7Z045FFG900-2, Digilent JTAG serial **210251842914**.
Two CERN FMC ADC100M4cha v6.1 cards occupy LPC/HPC; VADJ was measured at
2.5 V. Each card has an independent Si570/sample-clock domain. A WR-derived
software PI loop tunes each oscillator against the common reference.

Migen/LiteX → Yosys → patched nextpnr-xilinx/openXC7/Project X-Ray → PL bitstream.
The qualified integrated PL does not require Vivado. Keep pinned tool/database
versions and overlays; a clean build with arbitrary upstream versions is not
qualified. PS Linux uses its own DDR. The PL controls a separate 64-bit 1 GiB
SODIMM with LiteDRAM, two independent ADC packer/CDC/DMA paths and SFP Ethernet.

GP0 CSR aperture starts at `0x40000000`; GP1 PL DDR is
`0x80000000..0xbfffffff`. Default acquisition buffer offsets within PL DDR:
LPC `0x02000000`, HPC `0x10000000`. Installed `/etc/litex/csr.json` is the
address-map authority. Four channels × 16 stored bits ×100 MS/s =800 MB/s/card.
Finite captures are qualified; continuous Linux/network streaming is not.

## Verified status

| Element | Evidence and scope |
|---|---|
| SD boot / Linux / UART / DHCP / SSH | PASS; SD PL loading and automatic runtime, no JTAG intervention |
| Cold start | PASS after owner-reported power cycle; early BootROM/SPL/U-Boot UART and off duration not recorded |
| PL DDR | All eight lanes; three full 1 GiB BIST passes at startup |
| Independent ADC→DDR paths | Exact digital sequence and real ADC-pattern readback, zero drops |
| Analog | CH1 both cards: split AFG1062 1 MHz /1.001 Vpp, ±5 V range, analog50Ω OFF |
| Dual PLL | Automatic lock and sampled runtime status PASS; no continuous jitter qualification |
| SFP | External copper module, physical UDP/ICMP tests PASS |
| Reproduction without Vivado | Qualified integrated open-source PL and packaged Linux SD workflow available |
| Kasli-SoC physical port | Deferred until board supplied |

The 600.30 s soak verified784.5 MiB across20 dual captures, zero data errors/
drops,28000 exact UDP replies and80/80 ICMP. These were reused finite buffers,
not unique784.5 MiB address coverage or continuous streaming. Both PLLs were
locked in195 sampled observations with unchanged service PID.

Analog follow-up stored2 MiB/card; beginning/middle/end sine fits passed with
R²>0.99993, no clipping. Nominal uncalibrated amplitudes were LPC0.929 Vpp and
HPC1.021 Vpp. Separate capture epochs do not prove deterministic alignment.
After the power cycle: automatic DDR BIST,41.37 s sampled dual lock,
350 UDP replies,20/20 ICMP and four dual digital acquisitions passed.
Ext4 journal recovery completed after unclean power removal; no offline fsck or
power-loss endurance claim. See evidence directories linked below.

## Retained baseline and safe access

Last retained system: installed SD image, SD Wire **DUT**, automatic dual-PLL
service running; PID118 was historical, not an identifier to reuse.
Never switch a live rootfs to HOST or restore an older temporary-test golden
image automatically. QSPI and persistent U-Boot environment were not rewritten.

`/etc/init.d/S99integrated` starts `/opt/zc706-integrated/integrated_service.py`:
manifest verification → DDR training/BIST → SFP → ADC calibration → dual PLL.
Read `/run/zc706-integrated/service.log` and `pll.status.json`; require both
`cards[*].last.locked`, not just `state=running`. Stop the service before clock
initialization or programming. A preinitialized capture can coexist with it;
snapshot/restore ADC SSR, control, registers3/4 and DMA configuration. Never
reset only one side of an active DMA/FIFO. Older test wrappers may restore the
old golden bit or reset clocks: inspect them before using this installed runtime.

Read `/home/codex-hil/docs/pqc-coordination.md` and current AGENTS.md first.
Use sorted, nonblocking exclusive leases across identity checks, UART/JTAG/SPI/
network tests and restoration; release partial acquisitions if any is busy:

- `/home/codex-hil/.cache/zc706-210251842914.lock`
- `/home/codex-hil/.local/state/hil-storage/hil-storage-DP04I33Y.lock`

SD Wire serialDP04I33Y uses guarded HOST↔DUT APIs in lab-instruments. Its FT200X
CBUS0 was commissioned from AWAKE21 to IOMODE8 with EEPROM backup/readback.
It has no persistent OFF state. Preserve private EEPROM/card backups; follow
`lab-instruments/docs/sdwire-guarded.md`. Do not use a raw mux command as shutdown.

UART previously positively correlated with ZC706: CP2103 serial0001,
`/dev/serial/by-id/usb-Silicon_Labs_CP2103_USB_to_UART_Bridge_Controller_0001-if00-port0`,
115200. Shared workspace notes also associate this cable with FIT PM12: reverify
current cabling, acquire the corresponding PM12 lease if still shared, and check
for another reader. Never choose by ttyUSB number.

**IP addresses are historical hints.** Linux last used192.168.2.23 after DHCP;
new shared inventory assigns that address to Labcam2 on2026-10-30. Do not access
or administer a device by the old address alone. Reidentify through current
inventory/UART and strict SSH host key. Host identity files stay private:
`build/ssh/id_ed25519`, `/home/codex-hil/.local/state/zc706-sdwire-known-hosts`,
host alias `zc706-sdwire-mode-fix-20261027`. Do not disable host-key checks.
PL SFP static address192.168.2.206, MAC02:c0:de:70:60:01, UDP1234; verify route.
Last switch connection: first Netgear48-port switch, port52, FS copper1G SFP.
Earlier DAC connection did not establish the qualified link.

AFG1062 serial1544477 was reached through Pi gateway192.168.2.36:8840;
credentials/CA are private. The owner confirmed CH1 split to CH1 both FMCs.
Reconfirm physical wiring before future analog work. Both inputs are parallel:
one termination changes the voltage seen by both. Preserve generator state and
other output; the old configure script changes both outputs. Use a shared
instrument lease (`instrument-afg1062-1544477.lock`) for the whole experiment.

## Artifacts and reproduction

Known-good local SD artifact on Optiplex:
`/home/codex-hil/artifacts/zc706-integrated-standalone-sd-20261027-mode-fix/sdcard.img.gz`.

- Expanded335544832 bytes SHA256: `effe3ec9a450952cb57d917b790245bdf81025b7440ad823d9df951aae5305b8`
- Gzip SHA256: `5ca30585d6d4c92e1534592fc43bab919ad67b58e7dbc51fd67508650230680d`
- Qualified PL SHA256: `7bdc77eaf6176facf147f43d2c0ee2ed2833e5ea1057a644d2431be3e83ac831`

Adjacent manifest/offline audit/hardware-validation files identify contents.
The local artifact path is not a promise of a public release download.
Do not substitute the older image with non-executable ARM tools.

Follow [standalone build/installation](zc706-standalone-sd.md),
[soak/analog procedure](zc706-runtime-soak.md) and [ADC/DDR architecture](zc706-adc-ddr.md).
SD packaging reuses compiled baseline outputs; it is not itself a fresh rebuild
of all compilers/rootfs. Preserve matching bitstream, CSR, ARM tools and validation.

Heavy builds belong on Dell, hardware on Optiplex. Read the current
`docs/toolchains/heavy-builds-remote-handoff.md` on the host; use explicit
`dell-build sync kasli-linux`, `run`, `fetch`. Shared build lock is mandatory;
no nested flock, deletion of installations or interference with other jobs.
No fresh rebuild was performed for this handoff.

## Evidence and next entry point

- [Soak](../evidence/zc706/sd-runtime-soak-20261027/summary.json)
- [Analog](../evidence/zc706/sd-analog-live-20261028/validation.json)
- [Cold-start](../evidence/zc706/cold-sd-start-20261028/result.json)

Raw analog files remain in `build/analog-live-20261028T102134Z`; hashes in evidence.
Full soak archive is in `/home/codex-hil/artifacts/zc706-sd-soak-20261027/`.
Card/EEPROM backups are private, outside Git; original card backups cover the
partition/overwritten extent, not the complete32 GB medium.

Optional future ZC706 work, not reopening the closed milestone: analog CH2–CH4,
range/offset/amplitude calibration, controlled reference-loss/relock and SFP
unplug/relink during acquisition. Continuous streaming and deterministic shared
triggering require additional implementation.

When Kasli-SoC arrives: identify model/revision/part and connections; preserve
working ARTIQ as golden; reuse its PS7/DDR/MIO/clock/boot configuration. Start
with safe SD Linux and minimal AXI/CSR PL on that board. Do not copy ZC706
constraints, DDR or FMC assumptions. The physical Kasli milestone requires new
board-specific boot, memory, Ethernet and PS↔PL evidence.
