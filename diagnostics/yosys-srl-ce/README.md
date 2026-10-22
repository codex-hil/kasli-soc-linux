# Clock-enable loss in Yosys fixed SRL extraction

Confirmed with the project's Yosys0.52 (`fee39a3`), independent of LiteEth,
nextpnr, Project X-Ray or hardware. `shift.v` is a seven-stage enabled shift
register. `tb.v` compares it against an enabled FF reference, using nonconstant
LFSR data and periodic CE gaps.

The mapped SRL test fails at cycle6. The no-SRL control passes. A late-pass
trace shows seven FDRE with variable CE, then `xilinx_srl -fixed` creates
`$__XILINX_SHREG_` with E connected but ENPOL=2. Technology mapping consequently
ties SRL16E.CE high. This reproduces the ARP hardware/netlist corruption.

This is existing upstream [issue6058](https://github.com/YosysHQ/yosys/issues/6058),
fixed by [PR6059](https://github.com/YosysHQ/yosys/pull/6059), merged2026-07-22
(commit f9023e9). The fix sets ENPOL=1 for FDRE/FDRE_1. Do not submit a duplicate
fix or attribute this failure to nextpnr routing. The independently discovered
missing SRL timing coverage remains a separate limitation.

Run on Dell through the shared build lease:

```sh
dell-build sync kasli-linux
dell-build run kasli-linux build/python/bin/python tools/test_srl_enable.py \
  --output build/yosys-srl-ce-confirmed
```

To compare the already installed, pinned OSS CAD Suite20261005 Yosys:

```sh
dell-build run kasli-linux build/python/bin/python tools/test_srl_enable.py \
  --output build/yosys-srl-ce-suite --skip-trace \
  --yosys /work/build/tools/oss-cad-suite/bin/yosys \
  --cells-sim /work/build/tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v
```

The old-tool failure and trace are retained in
`evidence/zc706/srl-enable-20261022`. Replacement-tool test PASS: installed OSS CAD Suite20261005 contains
Yosys0.69+190, commit0e8336b4e. It preserves variable CE; mapped SRL and
no-SRL controls both pass. No replacement FPGA image or hardware
qualification is claimed yet. Next: map the actual ARP reproducer with
this pinned tool, then build and qualify hardware before promoting defaults.
