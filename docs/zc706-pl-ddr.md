# Independent ZC706 PL DDR bring-up

This target is independent of the FMC ADC target. No ADC data is connected
to the memory controller. Physical PL DDR validation is **pending**.

The ZC706 PL SODIMM is a 64-bit, 1 GiB MT8JTF12864 DDR3 module. The target
reuses LiteX-Boards' ZC706 DDR pin resource and LiteDRAM's `K7DDRPHY` and
`MT8JTF12864`, as in the upstream ZC706 target. It starts at 333⅓ MHz DDR
(667 MT/s), with an 83⅓ MHz controller and 200 MHz delay reference clock.
DDR uses fixed 1.5 V HP banks 33–35, independently of FMC VADJ.

PS FCLK0 feeds the PL MMCM. GP0, the LiteX CSR bus and DDR controller
use the resulting 83⅓ MHz system clock. The GP1 access frontend and BIST
run at 50 MHz, using upstream LiteDRAM native CDC into the 83⅓ MHz
controller and control/status CDC between BIST and the CSR bus.
GP0 exposes CSRs at `0x40000000`; GP1 exposes
the entire SODIMM at `0x80000000..0xbfffffff`. Linux PS DDR is separate.
GP1 uses upstream AXI-to-AXI-Lite/Wishbone bridges with registered channels;
GP0 remains the LiteX CSR bus. The PS already separates these windows.

## Build

```sh
make ddr-pl
make ddr-software
make ddr-test
make ddr-axi-test
```

The userspace program `build/zc706-ddr/pl-ddr-test` uses upstream LiteX
JEDEC initialization and leveling code, uncached `/dev/mem` mappings,
an address alias test and three full-capacity native BIST passes. It
destroys PL RAM contents. It must only be run with the matching DDR
bitstream and generated headers; this does not update the SD image or QSPI.

## Toolchain investigation, 2026-10-08

Yosys synthesis and the ARM static diagnostic build pass. Bitstream
generation and all physical memory tests remain pending.

The distributed Zynq chipdb lacks HP ILOGICE2, OLOGICE2, ODELAYE2 and
IDELAYE2_FINEDELAY
metadata. An isolated overlay imports these Series-7 HP definitions from
the pinned Kintex metadata. Upstream checkouts are kept unchanged.
`tools/ddr_chipdb.py` reproduces the database and records its SHA-256.

Database generation also needs an idempotent node-union guard and reduced
Python graph retention. These changes apply to an isolated generator copy.
The complete rebuilt database succeeds under a 6 GiB memory limit. Do not run
large RTL simulations concurrently with database generation. The original
nextpnr search without visited-node tracking exhausted host memory; builds
now have a 6 GiB RAM/no-swap limit and two CPUs to protect the host.

With HP metadata present, nextpnr binds the output delays. A diagnostic
build identified an input-delay search incorrectly accepting IDELAYCTRL
as an IDELAY site. The isolated patch
`patches/nextpnr-xc7-io-site-search.patch` makes that match precise and
prevents repeated graph visits. `tools/ddr_nextpnr.py` builds pinned
nextpnr with this patch without changing the upstream checkout.

The October OSS CAD Suite Yosys 0.69 experimental abc9 mapping retained
internal `$buf` cells. Converting those to connections disconnected
bidirectional DQ/DQS pads. This target therefore uses Debian snapshot
Yosys **0.52-2** with conventional ABC; ADC/probe retain their existing
suite. `tools/build_pl.py` rejects unmapped buffers and checks all 64 DQ
and eight differential DQS connections before placement. Stable synthesis
passes that check and nextpnr reaches logic placement.

The first shared-bus implementation routed but failed 100 MHz timing
(77.07 MHz maximum). It was rejected. The direct GP1 topology is being
validated; timing violations are not ignored.
The direct topology initially still failed at 75.99 MHz: the critical path
was the generic 32-to-512-bit native converter's read FIFO feedback.
The target now uses the native-width crossbar port and upstream Wishbone
frontend, matching normal LiteX SDRAM integration. A dedicated simulation
passes with sparse RAM across all 1 GiB address boundaries, native 64-byte
word selection, partial byte writes and backpressure.
Buffering the AXI channels alone still failed 100 MHz (55.27 MHz maximum).
The final topology separates the 50 MHz CPU memory-access frontend using
native CDC, preserving the 400 MHz DDR clock. The frontend simulation also
passes with actual 50/100 MHz clocks and asynchronous FIFO crossings.

The unused DQS input fix passed FASM-to-frames assembly on the rejected
100 MHz build. That artifact is not approved for programming: it failed
timing. The GP1 CDC build passed its 50 MHz domain (74.79 MHz maximum), but
failed the 100 MHz domain (84.41 MHz maximum). The remaining critical
path was BIST CSR base/end arithmetic. BIST now uses the upstream
control/status and native-port CDC wrappers at 50 MHz; the DDR controller
still runs at 100 MHz, with the physical DDR clock at 400 MHz. BIST ticks
therefore count 50 MHz cycles. This version routed at 93.81 MHz for the 100 MHz domain and was
rejected. The critical path had moved to CSR decoding. The bring-up target
now uses 83⅓ MHz system / 333⅓ MHz DDR clocks, with a 1000 MHz MMCM
VCO and integer output divisors 12/3/5/20. These preserve the 200 MHz
IDELAY reference and 50 MHz GP1/BIST clocks. The ARM initialization delay
and timer shim derive their cycles from generated CONFIG_CLOCK_FREQUENCY.
This reduced-clock target is being built.
The CSR wrapper simulation passes reset/start/configuration/status transfers
at 83⅓/50 MHz, including a deliberately injected memory error.

The backend currently strips `_T_DCI` from the upstream pin standards.
Digital impedance calibration/termination is therefore **not validated**.
The openXC7 HPCStore LiteX DDR demo uses SSTL15 without DCI, but that does
not establish signal integrity on this ZC706 SODIMM. This is a material
limitation for hardware tests and must be resolved or explicitly measured.
Reference: [openXC7 DDR demo constraints](https://github.com/openXC7/demo-projects/blob/main/litex-ddr-hpcstore-k420t/hpcstore_xc7k420t.xdc).

An additional packer fix avoids creating an input receiver for a differential
IOBUF whose O port is unused (the LiteDRAM DQS buffer). Otherwise FASM asks
for input features absent from the Zynq bit database. No FASM features are
silently removed from the resulting design.

## Hardware diagnostic

After a successful matching bitstream build, on the host:

```sh
make ddr-software
python3 tools/test_ddr_hardware.py --program
```

This selects only ZC706 JTAG serial `210251842914`, programs volatile PL
SRAM, uploads the diagnostic to the existing Linux and saves logs in
`build/zc706-ddr/hardware/`. No SD or QSPI writes occur. After a reconnect
or host reboot the existing USB grant script may need to be run through
sudo. Do not run the diagnostic while another user of PL RAM is active.

The wrapped-address BIST simulation passes with backpressure and both
sequential and PRBS data; a deliberately flipped bit produces exactly
one checker error. This is logic validation, not physical DDR evidence.
The synthesized target also passes 100 GP0 AXI CSR transactions with delayed
channels and response backpressure, plus DDR signature and PHY register
read/write checks. MMCM clocks are injected in this RTL simulation; it does
not validate the physical clock tree, PS7, GP1 RAM accesses or the DDR PHY.

| Element | Status |
|---|---|
| Independent DDR target | Implemented |
| Yosys | PASS |
| HP chipdb regeneration | PASS |
| ARM initialization/test program | Build PASS |
| nextpnr | HP metadata and site-search fixes being validated |
| Bitstream | Pending |
| DDR leveling and 1 GiB BIST on hardware | Pending |
| ADC-to-DDR connection | Deferred |
