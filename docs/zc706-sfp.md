# ZC706 PL SFP bring-up

This is an isolated diagnostic target, leaving the physically qualified dual
FMC ADC/PL DDR design available unchanged. It uses upstream LiteEth 1000BASE-X,
MAC, ARP, ICMP and UDP, with PS GP0 only for diagnostics. The PL has its own
MAC `02:c0:de:70:60:01`, IP `192.168.2.206`, and UDP echo port `1234`.
PS Linux Ethernet remains the separate management connection. GP0 ACLK is
explicitly driven by the 50 MHz system clock, matching the frontend; the
build checks this connection in the synthesized netlist.

The original 100 MHz system placement failed timing (77.54 MHz); the
diagnostic uses an integer MMCM ratio at 50 MHz with explicit constraints.
The complete MAC/preamble/CRC loopback also passes simulation across the
50 MHz / 125 MHz boundary.

## Hardware configuration

| Function | ZC706 connection |
| --- | --- |
| SFP TX P/N | W4/W3, GTXE2_CHANNEL_X0Y10, quad 111 |
| SFP RX P/N | Y6/Y5, same channel |
| Si5324 reference P/N | AC8/AC7, IBUFDS_GTE2_X0Y3, REFCLK1 of quad 110 |
| Channel reference selection | GTNORTHREFCLK1, CPLLREFCLKSEL=4 |
| Si5324 reset / interrupt | W23 / AJ25 |
| SFP TX_DISABLE_N | AA18, bank 9; board transistor inverts it |
| Board I2C | AJ14/AJ18, PCA9548 at 0x74 |
| SFP EEPROM | I2C mux channel 0, address 0x50 |
| Si5324 | I2C mux channel 4, address 0x68 |

Pins come from the pinned LiteX-Boards target and platform, AMD's
[UG954](https://docs.amd.com/api/khub/documents/m4fPXowvxKd5JZRfe046WQ/content)
and the official XC7Z045 FFG900 package file. An independent RapidWright
device query verifies the seven reference/data/control pin-to-site mappings.
[UG476](https://docs.amd.com/v/u/en-US/ug476_7Series_Transceivers),
pages 36–40, defines NORTH as the clock propagated from the quad below.
The Si5324 input is in quad 110 below the SFP channel in quad 111; hence
GTNORTHREFCLK1 and selector 4. This selection is checked after synthesis.

Si5324 uses the golden ARTIQ internal 125 MHz crystal profile: N1_HS=10,
NC1_LS=4, N2_HS=10, N2_LS=19972, N31=N32=4565, BWSEL=4, free-running
crystal on CKIN2. Register encoding and startup follow
`artiq-zynq/src/libboard_artiq/src/si5324.rs` and
`src/runtime/src/rtio_clocking.rs`. Only volatile registers are written;
I2C mux selection is saved/restored. The GTX CPLL runs at 2.5 GHz with
N1=4, N2=5, M=1, OUT_DIV=4, producing a 1.25 Gbit/s serial link.

## Architecture

The minimal PS7/GP0/CSR infrastructure is reused. GTX and LiteEth's software
8b/10b PCS provide 1000BASE-X autonegotiation, independent 125 MHz TX/RX
domains, and the upstream reset sequence. Complete-frame buffering prevents
underruns while crossing from the slower system clock to the 1 Gbit/s PHY. The MAC inserts/checks preamble,
padding and CRC. ARP and ICMP enable ping; UDP echoes payloads back to the
sender using a 2048-byte FIFO. A private EtherType 0x88b5 sends a deterministic
64-byte payload through the complete MAC/PCS/transceiver loopback path.

The system datapath is 8 bits at 50 MHz. This diagnostic establishes
functional Ethernet; it does not claim sustained 1 Gbit/s payload throughput.

## Open-source database additions

The pinned Zynq chipdb omits GTX BEL definitions; Zynq Project X-Ray also
omits GTX segbits and tile frame ranges. `tools/sfp_database.py` overlays the
pinned upstream openXC7 Kintex-7 GTX data without editing either upstream or
the installed toolchain. Frame geometry is checked against the XC7Z045 part
frame inventory and the rightmost INT column in each clock region. All
Kintex GTX tiles agree on frame count and word offsets. The device's existing
GTX tile/site descriptions are retained.

The AA18 bank-9 IOB pair is incorrectly listed as NULL. The adjacent LIOI3
already has its correct Zynq frame geometry. The overlay restores only this
pair using the existing XC7Z030 LIOB33 definition, physical sites verified
independently against XC7Z045, and the official bank-9 package functions.
The chipdb generator imports the five upstream Kintex GTX/IPAD/OPAD metadata
definitions; the existing HR package overlay adds AA18. The three upstream
TX BUFH buffers are replaced by BUFG buffers because nextpnr currently
places their reset-synchronizer consumers outside the reachable region. No Vivado is used.
These additions remain experimental until physical loopback qualification.

## Build and test

```sh
make BOARD=zc706 bootstrap
make sfp-test
make sfp-pl
.venv/bin/python tools/boot_adc_jtag.py --host 192.168.2.4 --sd \
  --bit build/zc706-sfp/gateware/gateware/top.bit \
  --output build/zc706-sfp/hardware/boot
```

The loader preserves QSPI, existing boot files and persistent U-Boot
environment. It loads a content-addressed PL file for this boot only.
Hardware orchestration runs on the host. If its local Python environment
has not been prepared:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
```

The host orchestrator uploads/checksums the inputs, saves boot and board
logs, and only runs external traffic tests after internal loopback and a
real external link:

```sh
.venv/bin/python tools/test_sfp_hardware.py --host 192.168.2.4 --program --external
```

Upload `tools/sfp_probe.py`, `tools/fmc_adc.py` and the generated CSR JSON to
Linux, then run:

```sh
python3 sfp_probe.py --csr-json csr.json --init-clock --loopback 1000 \
  --output loopback.json
python3 sfp_probe.py --csr-json csr.json --external --output external.json
```

Near-end PMA loopback (`LOOPBACK=2`) checks the numbered payload and frame
length; CRC/preamble error counters must remain unchanged. The receiver and
transmitter must initialize and PCS autonegotiation must finish. No SFP is
needed for this internal test.

External testing needs a suitable 1 Gbit/s SFP, cable and switch port capable
of 1000BASE-X. A 10G-only module/port is not sufficient. With internal loopback
disabled and an external link established, run on the host. UG954 also
documents J17 as a manual transmitter-enable jumper; a fitted jumper
forces the transmitter enabled independently of the FPGA output.

Run on the host:

```sh
python3 tools/test_sfp_network.py --output build/zc706-sfp/network.json
```

This checks 20 pings and 350 byte-exact UDP exchanges of varied sizes.
The PL endpoint is static; verify `192.168.2.206` is unused before connection.

## CSR map

GP0 CSR base is `0x40000000`, accessible via existing `/dev/uio0`.
Generated `csr.json` supplies the precise offsets.

| Bank | Registers |
| --- | --- |
| 1 | Existing scratch/counter/signature probe |
| 2 | Board I2C bitbang |
| 3 | SFP signature, control, GTX/PCS flags, Gray user/reference clocks, CPLL clock-loss flags |
| 4 | MAC preamble/CRC errors and accepted TX/RX frame counts |
| 5 | Numbered-payload start/busy, TX/RX frames, payload/length errors |

Control bits 0–2 select transceiver loopback, bit 3 drives Si5324 RESET_N,
bit 4 resets the PHY. Status bits 0–5 are CPLL lock, TX init done, RX init
done, TX MMCM lock, RX MMCM lock and PCS link. Bit 6 is Si5324 INT_N;
bit 7 indicates SGMII detection. Clock counters are Gray encoded. Additional
`clock_faults` bits 0/1/2 are reference clock lost, feedback clock lost and
CPLL reset. `si_ref_count` measures IBUFDS_GTE2.ODIV2 (half the Si5324 clock),
while `gt_ref_count` measures the CPLL-selected reference via GTREFCLKMONITOR.

An experimental control build can select the already configured 100 MHz
PS FCLK through the documented GTX GTGREFCLK fabric input:

```sh
make sfp-pl SFP_REFCLK=fclk
```

This isolates GTX/PCS/MAC testing from the dedicated inter-quad reference
route. `tools/sfp_nextpnr.py` applies an isolated patch preserving this fabric
input for routing, instead of discarding it as a dedicated hardwired GT
connection. The same patch prevents `CPLLREFCLKSEL` control pins from being
discarded by that rule; an independent post-route check verifies all three
selector connections and FASM routes. With 100 MHz, CPLL uses N1=5, N2=5, M=1, OUT_DIV=4, still
producing 1.25 Gbit/s. Dedicated external reference clock qualification is
tracked separately; the fabric reference is a diagnostic option.

## Status

| Element | Status |
| --- | --- |
| Numbered-payload logic simulation and negative cases | PASS |
| Complete MAC/preamble/padding/CRC simulation at 50/125 MHz | PASS |
| Upstream PCS/gearbox/autonegotiation suite, 25 tests | PASS |
| GTX/AA18 package mapping | Independently verified |
| SFP module identification on current hardware | No EEPROM response |
| Yosys / nextpnr / bitstream | PASS; setup and hold checks pass |
| Local quad-110 physical MAC/PCS/GTX loopback | PASS: 1000/1000 frames, zero errors, TX/RX ~125 MHz |
| Physical GTX DRP configuration readback | PASS: CPLL/dividers/CDR match generated configuration |
| Physical near-end PMA loopback | FAIL: reference-clock-lost remains asserted after backend fix |
| Switch link / ARP / ICMP / UDP | NOT_RUN |
| Combined ADC/DDR/SFP design | Deferred until isolated SFP qualification |

### Bring-up findings (2026-10-10)

The first 50 MHz target inherited LiteX's 100 MHz GP0 ACLK. UART boot
succeeded, but Linux MMIO could stall AXI. Explicitly assigning GP0 ACLK to
`sys` fixed it; Linux/SSH and repeated CSR reads then remained responsive.

GTX did not lock with either the dedicated reference or the FCLK control
variant. Inspection found that nextpnr's broad REFCLK-port rule removed the
three `CPLLREFCLKSEL` connections. The synthesized selectors were correct,
but the packed bits had no nets and FASM contained no selector routes.
The reference-selection patch and post-route guard address this defect.
The earlier source-bank GTREFCLK1_USED/COMMON activation experiments did
not restore a clock and are not part of the build.

Si5324 ICAL/LOL can initially look clear before calibration completes. The
probe now requires calibration clear and stable lock, with a 60-second
bound. All register writes remain volatile. Current failed attempts and
hardware diagnostics are retained in
[bring-up evidence](../evidence/zc706/sfp-20261010/bringup-attempts.json).

A system-clocked DRP bridge now reads the physical GTX CPLL, output-divider
and CDR registers. Eleven reads match the generated configuration exactly,
including CPLL N1=5/N2=5/M=1 for the 100 MHz fabric-reference variant. This
validates these configuration fields and DRP access, not the reference-clock
path or the Ethernet link. Corrected-selector and channel-reference-enable
control builds still report CPLLREFCLKLOST, with zero reference counters.

`make sfp-pl SFP_REFCLK=local` selects a diagnostic channel on unused HPC DP4
(AH2/AH1 TX, AH6/AH5 RX), in Si5324 quad 110, using local GTREFCLK1 and
CPLLREFCLKSEL=2. It isolates local reference bring-up from inter-quad routing;
it cannot test the physical SFP connector or switch. No ADC FPGA fabric pins
are used by this control build.

The local-quad control passed 1000/1000 complete frames with zero payload,
CRC or preamble errors on physical hardware. CPLL, TX/RX initialization,
MMCMs and PCS all locked; TX/RX and the selected reference measured about
125 MHz. Si5324 and local GTX operation are therefore confirmed. The ODIV2
fabric-monitor counter remains zero even in this passing design, so that
counter is not reliable evidence of a missing physical Si5324 clock. The
SFP quad and switch link still need separate qualification.

Further channel-GTREFCLK1_USED and source/common-plus-channel flag
experiments did not restore the SFP quad reference. RapidWright shows a
programmable BRKH_GTX mux between source REFCLK1 and target NORTHREFCLK1;
the pinned database has no BRKH_GTX segbits, and the current packer drops
this dedicated connection without configuring that mux. A source-clock
routing fix needs evidence for those bits, rather than guessing them.

The optional Vivado comparator can supply a routing reference. The offline
installer was found on GREG-CTI at `192.168.2.6`; its former address
`192.168.2.31` was unreachable. Zynq-7000 packages were installed successfully,
including the Enterprise device package needed to expose `xc7z045ffg900-2`.
The comparator reached synthesis, which failed with `Common 17-345`: no
Synthesis/XC7Z045 license is installed. This is a licensing limitation of the
optional comparator, not a dependency of the normal open-source build.
A model-only XC7Z030 experiment is being used to investigate GTX fabric-clock
configuration without an Enterprise license. Its bitstream must never be
programmed onto ZC706. No vendor bitstream has been loaded. The physical SFP
module EEPROM also did not acknowledge.

The [verified local-quad image and checksums](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-gtx-local-loopback-20261010)
are published separately from the ADC/DDR release. The hardware orchestrator
accepts `--build-dir` to test a saved artifact tree containing `csr.json` and
`gateware/{top.bit,manifest.json}` without replacing the normal build output.

### Optional vendor routing comparator

`tools/sfp_vivado_reference.tcl` consumes the same generated RTL/XDC and
writes into a separate ignored directory. It is not called by `make image`
or `make sfp-pl`, and it does not program hardware. The missing-part guard
was tested before the device addition. After installation, synthesis was
attempted and failed the license check; place/route and bitstream generation
for XC7Z045 have **not** been run. With an appropriate license, use:

```sh
vivado -mode batch -source tools/sfp_vivado_reference.tcl \
  -tclargs build/zc706-sfp/gateware/gateware build/zc706-sfp/vivado-reference
```

The intended comparison is the cross-quad reference mux, using source
Si5324 REFCLK1 and target SFP NORTHREFCLK1. A vendor reference would be
used to document the missing database bits; it is not the deliverable
open-source bitstream.

### Model-only fabric-clock comparator

The smaller XC7Z030 is supported by the free Standard license and has the
same GTX primitive. The following experiment generates two model-only
variants, with a 100 MHz fabric clock or a dedicated reference input:

```sh
python3 tools/sfp_fabric_reference.py
vivado -mode batch -source tools/sfp_fabric_reference.tcl \
  -tclargs build/zc706-sfp/fabric-refclk-fuzz/fabric \
  build/zc706-sfp/fabric-refclk-fuzz/fabric-output
vivado -mode batch -source tools/sfp_fabric_reference.tcl \
  -tclargs build/zc706-sfp/fabric-refclk-fuzz/local \
  build/zc706-sfp/fabric-refclk-fuzz/local-output
```

These model bitstreams must never be programmed on ZC706. The script
intentionally permits unassigned pads and the test-only GTGREFCLK DRC
(`REQP-52`); no such exceptions apply to the normal hardware build.
Both models completed synthesis, placement, routing and bitstream generation.
The fabric variant adds three channel bits: minor/word/bit `31/0/9`,
`31/0/10`, and `31/1/22`; no channel bits are removed. These are candidate
configuration bits, not a completed database fix. Physical validation remains
pending; this does not qualify a fabric reference for Ethernet operation.

### Physical fabric-clock experiment (2026-10-10)

The three vendor-model candidate bits were added to an otherwise unchanged,
timing-checked Yosys/nextpnr ZC706 fabric-reference design. All three are in
SFP channel minor 31: frame `0x0046329f`, word 57 bits 9 and 10, and word 58
bit 22. Decoding the assembled bitstreams confirmed exactly these additions
and no removed bits (frame ECC excluded).

On physical ZC706 the reference monitor measured about 100 MHz; CPLL,
TX/RX, MMCMs and PCS locked. The complete PCS/MAC PMA loopback passed
1000/1000 frames with zero payload, CRC or preamble errors, and TX/RX clocks
about 125 MHz. Linux boot and SSH also passed. This is the first physical
SFP-quad loopback success, using a bitstream assembled entirely by openXC7.
The reference is test-only PS fabric clock; the Si5324 cross-quad mux and
external switch link remain unqualified. Evidence: `evidence/zc706/
sfp-20261010/fclk-three-bits/`.

Reproduce the controlled configuration experiment with:

```sh
python3 tools/environment.py build/python/bin/python \
  tools/sfp_refclk_bit_experiment.py \
  --source build/zc706-sfp/fclk-bit-test \
  --output build/zc706-sfp/fclk-three-bits --openxc7 build/tools/openxc7
.venv/bin/python tools/test_sfp_hardware.py --host 192.168.2.5 --program \
  --build-dir build/zc706-sfp/fclk-three-bits --frames 1000
```

The source must first be built with `tools/build_pl.py --design sfp
--board zc706 --sfp-refclk fclk`, using the normal pinned environment.
This explicit experiment does not alter the default Si5324 build.

### Isolation of the required bit

A controlled physical comparison using identical routed logic established:

| Added channel-relative bits, minor 31 | Result |
| --- | --- |
| none | Reference lost, CPLL/PCS unlocked, loopback FAIL |
| 9, 10, 54 | 1000/1000 loopback PASS |
| 10, 54 | 1000/1000 loopback PASS |
| 10 | Reference lost, CPLL/PCS unlocked, loopback FAIL |
| 54 | 16/16, then 1000/1000 loopback PASS |

Thus only `31_54` is needed for this fabric-reference design. The isolated
GTX packer now records a nonconstant GTGREFCLK input, the FASM writer emits
`GTGREFCLK_USED`, and the Zynq database overlay maps that feature to `31_54`.
Donor databases and the ADC/DDR backend remain unchanged. The normal
`--sfp-refclk fclk` build passed setup and hold timing and emits this feature
automatically. Its physical qualification is independent of the manual
configuration experiment. Evidence: `evidence/zc706/sfp-20261010/
fclk-bit-isolation/`.

After the single-bit 1000-frame test, external mode was selected. Module
EEPROM at mux channel 0, address 0x50 returned NACK, so ICMP/UDP switch
tests were NOT_RUN. A loopback pass does not prove the module/link.

The integrated backend build was loaded and independently passed 1000/1000
physical loopback frames with zero errors. It was built and assembled using
Yosys/nextpnr/openXC7, with no manual configuration-frame edits. Bitstream
SHA-256: `297dd6d35e98d274c664b4525b5cbc3ec7754c680b9e3453e3a1f6764b1bb6ef`.
Linux boot, UART and SSH passed; current management DHCP address was
192.168.2.4. The checked loopback image is left running in volatile PL;
QSPI and the default SD boot configuration are unchanged. Evidence is in
`evidence/zc706/sfp-20261010/fclk-integrated/`.

[Published integrated SFP-quad diagnostic artifact](https://github.com/codex-hil/kasli-soc-linux/releases/tag/zc706-sfp-fclk-loopback-20261010).

### Upstream contributions

Submitted on the user's explicit instruction, with author and DCO sign-off
`Greg Kasprowicz <gkasprow@gmail.com>` and disclosed Codex assistance:

- [Project X-Ray PR #2576](https://github.com/f4pga/prjxray/pull/2576):
  randomized GTGREFCLK connectivity, usage tags, test-only DRC permission,
  regression tests and measured model/physical evidence. All four Python
  tests pass; the full randomized fuzzer with Vivado 2017.2 remains NOT_RUN.
  DCO and WIP checks passed; the PR is open for review.
- [openXC7/nextpnr PR #83](https://github.com/openXC7/nextpnr/pull/83):
  preserve selector/fabric clock nets and emit the GTX fabric-input feature.
  The patch applies to current main; hardware qualification used the pinned
  backend, so a full latest-main compile/hardware rerun is not claimed.

No direct generated-database PR was sent to prjxray-db, following its
contribution policy. The controlled port-only vendor comparison holds the
selector and dedicated input fixed and reproduces the same three-bit diff;
the physically required subset remains just bit `31_54`. Local copies of
the PR bodies, heads and check status are in
`evidence/zc706/sfp-20261010/upstream-reports/`. Submitted patch snapshots are
`patches/prjxray-gtx-fabric-refclk-fuzzer.patch` and
`patches/nextpnr-gtx-fabric-refclk-upstream.patch`.
