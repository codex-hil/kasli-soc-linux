# SRL16E isolation diagnostic

Current source is ABI3 (signature `0x53524c33`), work directory
`build/zc706-srl-inferred`. Dell setup/hold and physical comparison PASS on 2026-10-21.
Both inferred and explicit paths showed zero sticky errors over about45M
observed cycles. Evidence: `evidence/zc706/srl-inferred-20261021`.
Bitstream SHA-256: `929cb69748c2350342582f1b2b6307087f18f207ffcb7dbf945b1bb43cb7ab91`.
Golden restored with three whole1GiB DDR BIST passes; final management
IP192.168.2.10. Lease released and nonblocking reacquisition checked.
It compares byte delays4/8 from Yosys-inferred resetless chains (low16
error bits), explicit SRL16E plus final FF (high16), and fully observed FF
references. Runtime polarity stays zero during qualification and prevents
merging inferred storage with the reference. Do not change it during a test.
Synthesis inspection confirms 32 SRLs: 16 inferred tap3, 8 explicit tap2,
8 explicit tap6. Shared prefixes produce one four-cycle SRL per lane for
delay4 and two cascaded four-cycle SRLs per lane for delay8. This does not
exactly reproduce the Ethernet SRL topology; it tests basic inferred delays.
The checker traces each lane through SRLs and confirms total delay4/8,
constant CE, zero INIT and 32+64 observed reference FF bits.
`tools/test_srl.py` now requires ABI3; prior source revisions and physical
evidence below remain available in Git.

The following sections document ABI2 and ABI1 historical qualification.

Current revision is ABI2 (signature `0x53524c32`): two banks of sixteen
explicit SRL16E, both zero INIT. Low16 error bits correspond to variable CE;
high16 to CE tied high. Both banks have fully observed flip-flop references.
The first CE-pair build completed but did not enable mandatory hold checking;
it is NOT_ADMITTED to hardware. The replacement `build/zc706-srl-ce-pair-hold` build
passed setup/hold and physical qualification: all 32 taps show zero sticky
errors across about 45 million observed fabric cycles, for both CE modes.
Evidence: `evidence/zc706/srl-ce-20261021`.
Bitstream SHA-256: `b2a628480415bdd720cf99430915368b7e84748311bd814f43af3a3fc3e59a99`.
The PASS below belongs to ABI1, retained unchanged in evidence.
Use `build/zc706-srl-ce-pair-hold` for ABI2; do not overwrite ABI1 artifacts.
`tools/test_srl.py` now requires ABI2 and rejects an ABI1 bitstream.
`tools/check_srl_netlist.py` verifies the 32 SRLs, all taps in both CE modes,
zero INIT and 32 ordinary reference flip-flops before physical qualification.

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
  --board zc706 --design srl --output-dir build/zc706-srl-ce-pair-hold/gateware \
  --yosys /usr/bin/yosys --openxc7 build/tools/openxc7 --seed 3 --router router2
```

The bounded hardware wrapper owns the shared ZC706 lease throughout boot,
CSR testing and golden restoration/BIST. Its offline preflight verifies the
matching timing-clean build manifest. Run only with confirmed current management
IP (the U-Boot setup uses a random MAC, so DHCP addresses can change):

```sh
python3 tools/test_integrated_hardware.py --host CURRENT_IP \
  --work-dir build/zc706-srl-ce-pair-hold --output build/zc706-srl-ce-pair-hold/hardware \
  --srl-diagnostic-only --program
```

`tools/test_srl.py` is the board-side test, not a host lock owner; do not call it outside that lease.
It checks signature, ready, sticky errors and counter progress over ten samples.

The first attempt stopped before diagnostic programming because the previous
management IP no longer answered SSH. Golden restoration and DDR BIST passed;
the retry used the newly discovered address. This failure remains in evidence.

Next: compare explicit SRLs against Yosys-inferred delay chains matching the
Ethernet depths (24 tap2, 8 tap6, INIT zero). Both CE modes passed in ABI2;
constant CE alone does not reproduce the defect. The Ethernet SRLs also use
the same 50 MHz sys clock, as confirmed from synthesized clock connectivity.
This PASS
does not dismiss the existing controlled Ethernet SRL/no-SRL failure or identify
a faulty tool stage. Dynamic addressing and pre-warmup INIT remain untested.

Timing admission correction: ABI1 functional PASS remains valid, but its
manifest timing_passed flag did not include the dedicated hold gate. Do not
interpret ABI1 as hold-qualified. ABI2 host admission independently checks
reported setup, explicit hold result and primitive/reference inventory; a
manifest flag alone is insufficient. No new hardware access occurred here.

ABI2 restoration: golden boot PASS, GP1 smoke/address PASS and three
whole-1-GiB DDR BIST passes with zero errors. Final management IP
192.168.2.29; shared lease released and nonblocking reacquisition checked.

Next investigation: audit SRL data-input setup/hold coverage in nextpnr
and compare actual Ethernet SRL routes. Basic primitive, CE and inference
tests passed; the existing SRL-enabled Ethernet failure remains unresolved.
Do not attribute it to Yosys extraction without a reproducing case.
