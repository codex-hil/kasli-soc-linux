# SRL16E isolation diagnostic

Status: HDL generation passed on Dell on 2026-10-21; first open-source build
started. Hardware qualification is NOT_RUN. The qualified integrated image and
golden restoration image are unchanged.

`gateware/zc706_srl.py` uses PS7 GP0 CSR access and a 50 MHz fabric clock,
with sixteen explicit SRL16E primitives, static addresses 0 through 15,
INIT=0xa69c, LFSR input and periodic CE gaps. A fully observable 16-bit
flip-flop reference prevents shift-register extraction for the reference.
After sixteen enabled shifts, a sticky per-tap mismatch mask compares the
primitive outputs against the reference on every fabric cycle. This does
not qualify initialization before the warmup, dynamic addressing or SRLC32E.

The target reuses the SFP target's patched packer/database to isolate the
primitive in the same implementation flow, without Ethernet, ADC or DDR logic.
It cannot by itself attribute a failure to a particular tool stage.

From Optiplex:

```sh
dell-build sync kasli-linux
dell-build run kasli-linux build/python/bin/python tools/build_pl.py \
  --board zc706 --design srl --output-dir build/zc706-srl/gateware \
  --yosys /usr/bin/yosys --openxc7 build/tools/openxc7 --seed 3 --router router2
```

Before hardware use, inspect synthesis to confirm explicit SRLs survive and
the reference remains flip-flops; require timing and hold admission. Add this
target to a bounded hardware wrapper that owns the shared ZC706 lease throughout
boot, CSR testing and golden restoration/BIST. `tools/test_srl.py` is the
board-side test, not a host lock owner; do not call it outside that lease.
It checks signature, ready, sticky errors and counter progress over ten samples.

Next: collect the build and primitive inventory, implement locked qualification
with automatic golden restoration, then run the physical test. Preserve failed
results; a PASS here would require more targeted SRL tests, not dismiss the
existing controlled Ethernet SRL/no-SRL failure.
