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

An optional Vivado comparator could supply the missing routing reference.
The shared installation currently has Artix-7 and ZynqMP support, but no
Zynq-7000/Kintex-7 device parts. Adding Zynq-7000 from the cached offline
installer failed validation before installation because packages are missing;
its original NAS archive at `192.168.2.31` is unreachable. No Vivado
bitstream was built or loaded, and the normal build retains no Vivado
dependency. The physical SFP module EEPROM also did not acknowledge.
