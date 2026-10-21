# SRL16E isolation diagnostic

Status: open-source build and physical SRL16E comparison PASS on 2026-10-21.
Sixteen explicit SRL16E and sixteen reference flip-flops (8 FDRE, 8 FDSE)
survived synthesis; all SRLs use 6LUT sites. Ten samples spanning about
45 million fabric cycles showed ready=1 and sticky errors=0. The qualified
integrated image and golden restoration image are unchanged.

Bitstream SHA-256: `4a969072571d03d22566a9834e631c504508c992332951f984872ce7f1aef12f`.
Evidence: `evidence/zc706/srl-20261021`.

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

The bounded hardware wrapper owns the shared ZC706 lease throughout boot,
CSR testing and golden restoration/BIST. Its offline preflight verifies the
matching timing-clean build manifest. Run only with confirmed current management
IP (the U-Boot setup uses a random MAC, so DHCP addresses can change):

```sh
python3 tools/test_integrated_hardware.py --host CURRENT_IP \
  --work-dir build/zc706-srl --output build/zc706-srl/hardware \
  --srl-diagnostic-only --program
```
 `tools/test_srl.py` is the
board-side test, not a host lock owner; do not call it outside that lease.
It checks signature, ready, sticky errors and counter progress over ten samples.

The first attempt stopped before diagnostic programming because the previous
management IP no longer answered SSH. Golden restoration and DDR BIST passed;
the retry used the newly discovered address. This failure remains in evidence.

Next: isolate CE tied permanently high, matching all 32 failing Ethernet SRLs
(24 tap2, 8 tap6, INIT zero), versus the working variable-CE case. This PASS
does not dismiss the existing controlled Ethernet SRL/no-SRL failure or identify
a faulty tool stage. Dynamic addressing and pre-warmup INIT remain untested.
