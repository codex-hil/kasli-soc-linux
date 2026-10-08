# Independent ZC706 PL DDR bring-up

This target is independent of the FMC ADC target. No ADC data is connected
to the memory controller. Physical PL DDR validation is **pending**.

The ZC706 PL SODIMM is a 64-bit, 1 GiB MT8JTF12864 DDR3 module. The target
reuses LiteX-Boards' ZC706 DDR pin resource and LiteDRAM's `K7DDRPHY` and
`MT8JTF12864`, as in the upstream ZC706 target. It starts at 400 MHz DDR
(800 MT/s), with a 100 MHz controller and 200 MHz delay reference clock.
DDR uses fixed 1.5 V HP banks 33–35, independently of FMC VADJ.

PS FCLK0 feeds the PL MMCM. Both PS AXI GP ports and the LiteX bus use the
resulting 100 MHz system clock. GP0 exposes CSRs at `0x40000000`; GP1 exposes
the entire SODIMM at `0x80000000..0xbfffffff`. Linux PS DDR is separate.

## Build

```sh
make ddr-pl
make ddr-software
make ddr-test
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
The first rebuilt database succeeds under a 6 GiB memory limit; the final
overlay including the HP input-delay variant is being rebuilt. Do not run
large RTL simulations concurrently with database generation. The original
nextpnr search without visited-node tracking exhausted host memory; builds
now have a 6 GiB RAM/no-swap limit and two CPUs to protect the host.

With HP metadata present, nextpnr binds the output delays. A diagnostic
build identified an input-delay search incorrectly accepting IDELAYCTRL
as an IDELAY site. The isolated patch
`patches/nextpnr-xc7-io-site-search.patch` makes that match precise and
prevents repeated graph visits. `tools/ddr_nextpnr.py` builds pinned
nextpnr with this patch without changing the upstream checkout.

The wrapped-address BIST simulation passes with backpressure and both
sequential and PRBS data; a deliberately flipped bit produces exactly
one checker error. This is logic validation, not physical DDR evidence.

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
