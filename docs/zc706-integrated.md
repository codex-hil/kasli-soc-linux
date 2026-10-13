# ZC706 integrated acquisition and clock discipline

Development target: `make integrated-pl`. This reuses the qualified dual-card
ADC/DDR target and the SFP subsystem, adding two original WR DDMTD detectors.
Physical integration validation is pending; standalone subsystem results do not
qualify this target.

The DDR controller remains at 83 1/3 MHz, with its qualified MMCM and BUFG
placements. The WR helper is derived directly from PS FCLK0 (100 MHz), at
98.4375 MHz; both ADC sample clocks are compared to FCLK0. ADC receivers and
DMA retain independent domains and asynchronous FIFOs. PLL locking does not
establish a shared acquisition epoch.

CSR banks 1–15 retain the ADC/DDR ABI. Reciprocal counters occupy 16–18,
WR phase detectors 19–20, and SFP diagnostics/MAC/packet test 21–23.
Reciprocal timestamps use the DDR system clock; software uses the exported
reference frequency rather than assuming 100 MHz. Phase units remain 10/63 ns.
SFP uses the physically qualified PS FCLK 100 MHz reference, the existing MAC/IP and UDP echo port.
Board I2C is shared by control software; it must have one owner per transaction.

Initialize DDR and train both receivers before starting the dual PLL runner
with `--preinitialized`. Do not initialize/reset receivers while acquisition
or the PLL control loop is running. No flash, OTP or default SD boot changes.

Build and verification commands:

```sh
make integrated-pl integrated-software
python3 tools/test_integrated_hardware.py --host BOARD_IP --program --output build/zc706-integrated/hardware
```

The host wrapper first trains DDR and performs full-capacity BIST.
It then trains both receivers before the phase-control run.
The host wrapper owns the ZC706 lock throughout JTAG boot, training and tests.
It uses volatile JTAG programming, verifies uploaded file hashes and retains
logs, phase records and board-side capture results. The initial test includes
1,000 complete SFP MAC/PCS/GTX loopback packets. External tests use ICMP and
byte-exact UDP echo through the switch while acquisition and PLL control run.

Regression checks passed: independent-clock ADC DMA simulation (stalls,
overflow, reset, frame failure, invalid configuration), original WR dual
DDMTD simulation, PI model, I2C fault handling and parallel control ownership.
Standalone SFP register addresses and widths remain unchanged; the reference-monitor constant is additive.

Clock-placement findings: unconstrained TX MMCM placement could not route a
clock to its BUFG. The target retains the qualified SFP TX MMCM/BUFG sites,
DDR sites and reserves other available MMCMs for RX, the WR helper and ADC2.
The dense design also exposed an expensive MMCM-LOCKED to GTX-TXUSERRDY
route. The integrated target synchronizes each SFP MMCM LOCKED output through two
SYS flip-flops placed adjacent to the MMCM, before all downstream consumers
(including TXUSERRDY and reset logic); the isolated target keeps its qualified
behavior. This
delays READY until the user clock is stable and still requires physical
startup/loopback validation.

The qualified isolated SFP image uses FCLK; the Si5324 inter-quad path remains
unqualified. External switch operation was NOT_RUN in that qualification
because module EEPROM returned NACK. The integrated wrapper attempts the
external test and records PARTIAL rather than PASS if it fails, even when
DDR, both ADC streams, both PLLs and internal SFP loopback pass.

During concurrent DDR readback the bounded PLL process uses SCHED_FIFO
priority 10, inherited by its two native I2C workers. Each control iteration
sleeps, I2C failures have bounded timeouts, and the process terminates after
120 seconds, restoring both RFREQ settings. DDR readback uses normal priority.
This protects control deadlines from a CPU-bound diagnostic reader; the
reported phase statistics must still pass during the actual readback interval.

Two optional SFP reference-clock diagnostic counters are omitted in the
integrated target (`SFP_REFERENCE_MONITORS=0`), freeing their two BUFGs and
clock domains. Their CSR values stay zero; TX/RX frequency counters, PHY/PLL
flags and DRP remain active. The isolated SFP target retains both monitors.
The initial placement used twelve distinct BUFG clocks in each of two regions.

An isolated backend extension fixes router1's consistency check for a
reserved source wire before any sink arc is routed. Other wires remain
subject to the full consistency check. `NEXTPNR_ROUTE_SNAPSHOT` optionally
saves the placed state at routing entry to speed backend experiments.


### Integration routing checkpoint — 2026-10-11

No integrated bitstream has passed routing and timing, and no integrated
hardware qualification has run. The existing clock-only image remains on
ZC706. Yosys and all three regression suites passed; matching software built.

Router2 searched individual hard clock arcs for millions of steps. Router1
also slowed on the same placement. Diagnostic logs are preserved under
`evidence/zc706/integrated-20261011`. Moving two BUFG index-zero allocations
in an experimental placement eliminated the corresponding initial blocked
clock arcs, but MMCM-to-BUFG routes remained expensive, including DDR's
unchanged clock placement. This does not yet establish the root cause.
The preliminary SYS timing estimate was 74.92 MHz versus 83.33 MHz;
final timing has not been obtained and must pass before programming.

The isolated backend now prints clock-root connectivity, reservation checks
and progress every 100,000 search iterations. It writes the placed state to
`top_placed.json`; this enables offline rerouting without repeating synthesis
and placement. JSON snapshots retain a `settings.router` value, which must
also be changed when comparing routers. Development placement experiments
are not release images and must not be assembled or programmed as qualified
builds. Next: trace a legal MMCM-to-BUFG path against forward router expansion,
repair the measured issue, rerun the reproducible build and all setup/hold
checks, then run `test_integrated_hardware.py --program` under the board lock.


A bounded, architecture-availability-aware forward BFS for DDR CLKOUT0 and
SFP RX CLKOUT0 reached 250,008 vertices each with 180,245 vertices pending,
without finding the sink. This is an inconclusive budget-limited result,
not evidence that a route is absent. The optional `NEXTPNR_CLOCK_BFS=1`
diagnostic performs no routing mutations. Next diagnostic: bidirectional
search from the MMCM output and BUFG input, checking sink ownership and
uphill connectivity before changing placement or hardware parameters.

The subsequent bidirectional search also reached its 500,000-vertex budget.
SFP RX visited 237,428 forward and 262,574 backward vertices; DDR visited
238,516 forward and 261,490 backward vertices. Both queues remained nonempty.
This remains inconclusive. The diagnostic preserves availability and ownership
checks and does not bind any routing resources. Its bounded routing run was
stopped after 120 seconds; no hardware action occurred. Next: inspect a search
restricted to dedicated clock resources and compare its stopping edges with
chip database connectivity and router reservations.

### Confirmed clock database export defect — 2026-10-11

The pinned nextpnr exporter deliberately filtered `CK_BUFG_CASCIN` to
`CK_BUFG_CASCO` PIPs in `CLK_HROW_TOP` tiles. This prevented MMCMs farther
from the central BUFG row from using the dedicated clock cascade. A controlled
comparison used the identical placed JSON, XDC and diagnostic backend with
only the chip database changed: both DDR CLKOUT0 and SFP RX CLKOUT0 were
disconnected in the restricted clock graph before the fix and connected after
it. The restored paths explicitly traverse the previously filtered cascade
PIPs. The qualified standalone SFP RX MMCM sits in the nearest region, so its
route did not need those PIPs. The qualified DDR SYS route instead traversed
general fabric and a LUT; it was not a dedicated-route reference.

`patches/nextpnr-clock-cascade.patch` contains the exporter change.
`ddr_chipdb.prepare(clock_cascade=True)` applies it in an isolated generator
and checks all 32 restored PIPs against Project X-Ray configuration features.
The integrated build now uses its own `chipdb-cascade` and `chipdb-cascade-hr`
outputs. Existing ADC, DDR and standalone SFP databases remain untouched.
The default generator mode and its cache identity remain unchanged.

Evidence: `evidence/zc706/integrated-20261011/clock-cascade-{baseline,fixed}.json`,
compressed connectivity logs and the complete audited feature list. This is
a connectivity fix; full routed timing and physical integration remain pending.

To probe a generated placement without programming hardware:

```sh
python3 tools/environment.py build/python/bin/python tools/diagnose_integrated_clocks.py \
  --json build/zc706-integrated/gateware/gateware/top_placed.json \
  --xdc build/zc706-integrated/gateware/gateware/top.xdc \
  --chipdb build/zc706-integrated/chipdb-cascade-hr/chipdb-xc7z045.bin \
  --output build/zc706-integrated/clock-connectivity
```

The probe intentionally exits before the main router, checks neither final
timing nor bitstream correctness, and searches a subset selected by clock PIP
names. `--topology-only` ignores occupancy/availability for diagnosis and must
never be interpreted as proof of a programmable route.

A compact reproducer is now committed as `clock-cascade-reproducer.json` and
`.xdc` in the same evidence directory: only two placed MMCMs and two BUFGs,
8.7 kB of JSON. It reproduces both disconnected baseline paths and both
connected fixed paths without the ADC/DMA/MAC design. Its MMCM inputs and
feedback are intentionally absent: it is a routing-graph reproducer only,
not synthesizable or programmable gateware. Use these two files as the probe's
`--json` and `--xdc` arguments to reproduce the database comparison.

The ordinary nextpnr `preRoute` pass binds available dedicated clock routes
before the diagnostic inspects the graph. The diagnostic search itself binds
no resources, changes no input files and emits no bitstream.

### BUFG0 pseudo-PIP ownership defect — 2026-10-11

A second controlled reproducer shows `adc2_rx.dco` using the tile pseudo-PIP
`CLK_BUFG_BUFGCTRL0_I0 -> CLK_BUFG_BUFGCTRL0_O`. That wire belongs to the
separately instantiated SFP TX input BUFG. The source site pin is a different
node, so the clock pre-router failed to protect the buffer's output tile wire.
The SFP clock then had no dedicated route into its MMCM. Blocking just this
pseudo-PIP changes the output owner from `adc2_rx.dco` to the expected
`pma_k7_gtx_basex_s7mmcm0_clkin_signal` and removes those input routing failures.
The proper instantiated-buffer path from site O to the tile output remains
available. `patches/nextpnr-bufg0-no-routethrough.patch` records the guard,
which is enabled by default in the isolated integrated backend.

The evidence directory contains `bufg0-reproducer.{json,xdc}` and compressed
baseline/blocked logs. The two controlled runs used one experimental backend
with its guard toggled by environment; the production helper now always
enforces the guard. Physical validation remains pending.

The first complete placement stopped at snapshot writing because a relative
output path was interpreted from the gateware subprocess directory. This was
a build wrapper bug; `NEXTPNR_ROUTE_SNAPSHOT` now uses an absolute path.

### Complete main route, pending hold and setup — 2026-10-11

Both clock fixes allowed the full placed design to finish its main route
(178.46 s) and the first hold-buffer reroute (41.49 s). The clock-source
ownership check passed for the full pre-router state. No bitstream was
qualified or programmed. Hold pass 0 inserted eight buffers and left three
violations; the next pass asserted when reusing a rolled-back buffer's net
alias. The isolated helper now uses a separate monotonic allocation counter,
checks both cell names and net aliases, and removes the new self-alias when
rolling a buffer back. The patch is `nextpnr-hold-buffer-unique-names.patch`.
Compilation passed; completion of actual hold repair remains pending.

The old placed JSON snapshots also dropped clock constraints. Since
`--no-pack` skips the XDC packing stage, the reroute incorrectly used the
default 100 MHz on every domain, including SYS and GP1. That timing result
is invalid. Snapshot hooks now serialize min/max period, high time and low
time in native timing units, and restore all six fields before routing.
Production replay rejects old snapshots without clock metadata; graph-only
diagnostics may still inspect them without generating a bitstream.

The build additionally checks the reported constraint frequencies against the
actual integrated clock plan and rejects foreign ownership of driver output
wires. Negative tests rejected the measured BUFG0 misroute and the incorrect
100 MHz SYS constraint; correctly owned roots and the 83.33/50 MHz SYS/GP1
constraints passed. A fresh full build will produce proper constrained timing.
The previous reroute's long path was CSR address decode to a distant register
enable (1.30 ns logic, 15.74 ns routing); if it remains failing with valid
constraints, repair the CSR placement/decode path instead of relaxing timing.

The offline regression `tools/test_integrated_clock_snapshot.py` passed with
the production backend: a snapshot retaining `pack=1` but missing timing
metadata is rejected before routing, and six native timing fields are restored
on each of two annotated clock nets. Results are in `snapshot-regression.json`
and compressed missing/restored logs. Run it through `tools/environment.py`.
It tests replay restoration; full-build snapshot emission and timing remain
separate checks. A fresh build with all fixes and verbose hold diagnostics is
running with a 1500-second bound.


### Native-clock full build: BUFG1 conflict (2026-10-11)

The fresh full build emitted all six native timing fields on 27 clock nets.
SYS has a 12,000 ps period, GP1 20,000 ps and ADC IO 2,500 ps, so the
snapshot now preserves the intended 83.33/50/400 MHz constraints.
However, the full route stalled before setup/hold evaluation: ADC2 DCO
claimed `CLK_BUFG_BUFGCTRL1_O`, owned by the ADC1 IO clock. The original
BUFG0-only guard was insufficient. The same database exposes 16 identical
I0-to-O pseudo-PIPs in each BUFG tile; the isolated helper now rejects
this class for every buffer index while retaining the real site-output PIP.
Evidence is `native-clock-bufg1-conflict.json` and the compressed full log.
A bounded native-constraint snapshot replay is also running to separate
preroute state from main-router timing. Neither route is qualified for hardware.

Both host filesystems ran low on free space during this attempt. Only the
reproducible intermediate cascade BBA was removed; its binary chip database,
audit, golden images and hardware evidence remain intact. Direct use of the
existing resource-limited container avoids a Docker configuration update;
compiler temporary files must still use `/work/build/tmp`. A link attempt
without that temporary-directory setting failed with ENOSPC.

The native-clock replay completed routing and both hold repair passes without
an alias assertion. Eight buffers were inserted; three ADC2 FIFO-to-BRAM
arcs remain because their source slices have no output mux available.
SYS setup still fails at 58.67 MHz against 83.33 MHz, while GP1 passes at
57.64 MHz against 50 MHz. This confirms the hold-name crash fix but does
not qualify the design. The next implementation steps are to localize CSR
address/decode without changing transaction latency and repair the three
remaining hold arcs without accepting timing failure.

The generalized BUFG guard compiled successfully with project-local temporary
storage. A controlled probe after clearing all 70,069 serialized routing
attributes restored 27 clock constraints, connected both tested MMCM/BUFG
paths, and reported no foreign owners of clock-root outputs. ADC1 IO's
BUFG output now belongs to `adc_rx.io_clk`. This is a preroute regression,
not proof of full setup/hold closure or hardware operation. The raw database
contains 16 such I0-to-O pseudo-PIPs in each of BOT and TOP tiles (32 total).


### Per-bank CSR address replication (2026-10-11)

The integrated target now replicates the registered Wishbone2CSR address
into one set of explicit DONT_TOUCH FDREs per CSR bank. The replicas capture
and clear from the same FSM branches as the upstream register; they add no
transaction cycle. CSR write/read strobes, data and response mux retain the
existing LiteX interconnect. The helper rejects unexpected bridge/interconnect
structure instead of silently accepting a different bus implementation.
Only the integrated target uses this change; standalone golden targets remain
unchanged. The exported CSR bases and register map match the previous image.

`tools/test_csr_address_replication.py` compares the original and replicated
bridges cycle by cycle. All 450 deterministic transactions passed, including
mapped/unmapped reads and writes, zero/partial/full byte masks, idle gaps and
resets. ACK, read data and all scratch storage values are checked. Explicit
FDRE instances use a synchronous model for simulation; this is not physical
timing validation. Run with the project build Python in its container.

A fresh full synthesis/place/route with native clock constraints and the all-BUFG
pseudo-PIP guard is running (`csr-replicated-full.log`). Its timeout is inside
the container, so expiry terminates the build process group there. Setup/hold
closure, the three prior FIFO hold arcs and physical integrated validation
remain pending. No hardware was accessed during this implementation.


### Transactional hold detour rollback (2026-10-11)

A hold detour that reached the sink but failed to accumulate the requested
delay previously bound its path as LOCKED before returning false. The fallback
therefore ran on a modified route even though the attempt reported failure.
The isolated helper now tests the accumulated delay before binding and rolls
back the original private branch on failure. A successful detour commits as
before. This does not change any timing requirement or accept a violation.

`tools/test_hold_detour_rollback.py --source <hold_fix.cc>` compiles and executes
the actual C++ detour function with a minimal graph context. The original
function fails the insufficient-delay rollback assertion; the patched function
passes both failure rollback and successful longer-path cases. The harness
checks path PIPs and binding strength, but does not model FPGA site legality.
Full nextpnr/physical qualification remains separate. The running CSR build
uses the backend loaded before this rollback change; do not attribute its
results to the new patch.

Yosys retained 332 used per-bank address FDRE cells from the CSR replication.
The fresh CSR build has reached routing. Placement estimates are not final
setup/hold qualification.

The rollback regression also covers an initially LOCKED private branch.
Rollback now restores each saved binding strength as well as its PIP;
otherwise a failed attempt would downgrade a previous locked route to STRONG.
All four graph cases (short/long path, STRONG/LOCKED initial binding) pass.


### First complete integrated bitstream and hardware comparison (2026-10-11)

The CSR-replicated full build passed setup in every reported domain and hold
with zero remaining violations after nine feedthrough buffers. Final SYS Fmax
is 85.56 MHz against 83.33 MHz; GP1 is 55.70 MHz against 50 MHz. All 22
requested ADC differential terminations were emitted. Qualified bitstream SHA:
`2cd907d2308cbc77a89b4b5a08c7ee7ceeb130c8cb013b92fb1d6f467cc943c9`.
This run used the pre-rollback backend, as noted above.

Volatile JTAG programming, DONE, U-Boot CSR signature, Linux/UART and management
Ethernet/DHCP/SSH passed. Linux initially obtained 192.168.2.7. PL SODIMM
training/memtest failed, so integrated ADC capture, SFP and dual PLL tests were
not run. Internal nextpnr timing closure alone does not prove the external DDR
interface. The same DDR test binary passed on the golden ADC+DDR image, with
three complete 1 GiB random BIST passes and zero errors. It failed on integrated
PL again; a diagnostic command-delay override of 15 taps (golden calibration)
also failed. Thus neither the test binary nor this single delay setting explains
the regression. Matched DDR primitive parameters and all 38 DDR MMCM FASM
configuration lines are identical to golden.

Both experiments held the shared ZC706 lock throughout programming/UART/SSH/
testing/restoration. No SD, QSPI, OTP or persistent boot environment was written.
The golden ADC+DDR image was restored and passed another three whole-memory
BIST passes. Current management DHCP: 192.168.2.11. Hardware results and logs
are recorded under `evidence/zc706/integrated-20261011`. Next work is comparison
of DDR I/O placement/routing/FASM against this confirmed physical baseline;
this is an integration regression, not evidence that the SODIMM is defective.


### DDR byte-lane localization (2026-10-11)

`pl-ddr-test --diagnose-errors` writes four fixed patterns over 32 KiB and
counts read XOR failures per byte of each 64-bit DDR word. It may run after
training failure to gather evidence, but never turns failed initialization
into a successful qualification. The same binary reported 13,356 byte errors
only in lane 4 (DQ32..39) on integrated PL; all seven other lanes had zero.
Golden PL reported zero for all lanes, then passed three whole-1-GiB BIST runs.
The board remains on golden ADC+DDR at 192.168.2.13. Logs and per-lane counts
are in `lane-hardware-result.json` and `lane-error-summary.json`.

`tools/compare_ddr_reference.py` reproduces the offline comparison. All 528
non-ADC DDR I/O resource locations/types/parameters and 4,452 static I/O FASM
features match. Both DDR MMCM-to-BUFG input routes changed from fabric/LUT
paths in golden to dedicated clock cascades in integrated. This is a route
difference, not an established cause of the isolated lane failure.

`tools/test_ddr_reference_hardware.py --host <current-IP> --output <directory>`
repeats candidate/golden lane diagnostics under one shared ZC706 lock and
restores the golden image followed by its full BIST. Build diagnostic software
with the current `software/pl_ddr/main.c` first. Existing images require their
matching timing-clean manifests. The wrapper uses volatile JTAG and `/tmp`
uploads, without SD/QSPI writes. The next investigation is lane-4-specific
read/write/control routing and its clock sinks against the working reference.

### DDR delay-control sink audit (2026-10-11)

`tools/audit_ddr_delay_routes.py` checks serialized route destinations for
C/CE/LD/INC/LDPIPEEN on every non-ADC IDELAY/ODELAY. Golden and integrated
both contain 171 delay cells and all 855 checked control sinks. Removing
DQ32 IDELAY CE from a copy of the routed design produces exactly the expected
single missing-sink error. Results are recorded in
`evidence/zc706/integrated-20261011/ddr-delay-control-audit.json`.
This excludes absent serialized control sinks; it does not prove correct
logical drivers, FASM encoding, electrical timing, or physical connectivity.
No hardware was accessed for this audit. Next compare lane-4 control logic
and route-to-FASM coverage against adjacent working lanes and golden.

### DDR control LUT encoding audit (2026-10-11)

`tools/audit_ddr_control_luts.py` checks emitted FASM INIT truth tables against
packed logical INIT and original-to-physical input mappings for the CE/LD
LUT drivers of DDR delay cells. Each image has 50 driver outputs; all match
for every physical input assignment allowed by constant-connected pins.
Shared O5/O6 LUTs require respecting the tied-high A6 input of O6; checking
its unused lower INIT half would incorrectly report the neighboring O5
function as a mismatch. A deliberately inverted emitted INIT is detected.
The fixture leaves original build artifacts unchanged.
Evidence: `evidence/zc706/integrated-20261011/ddr-control-lut-audit.json`.
This rules out INIT pin-permutation encoding errors in these control LUTs,
not wrong upstream logical drivers, missing routing configuration bits,
external timing, or electrical faults. No hardware access occurred.
The next check is the lane-4 route PIP encoding and upstream training-pulse
logic relative to golden and neighboring functioning lanes.

### DDR routing feature-presence audit (2026-10-11)

`tools/audit_ddr_route_fasm.py` selects delay C/CE/LD nets and all nets of
52 I/O/serializer/delay cells associated with eight byte-4 DQ pins and two
DQS pins. Shared clocks and constants expand coverage across the design.
Tile PIPs are matched to tile-type JSON and emitted FASM. Database ppips
are classified separately: initial apparent omissions on eleven output
edges are `always` entries, present in both candidate and golden routing.
Candidate has 33,137 ordinary emitted real PIPs; golden has 28,581, with
zero missing ordinary features. Removing an included real feature from a
fixture is detected; original artifacts remain intact.
Site-internal/boundary edges and database default/hint/pseudo entries are
explicitly unproven by this feature-presence audit. It does not check assembled
configuration bits or hardware timing. No hardware access occurred.
Evidence: `evidence/zc706/integrated-20261011/ddr-route-fasm-audit.json`.
Next investigate the upstream training-pulse/read-bitslip logic and lane-4
site mux encoding; integrated DDR remains FAIL, golden remains restored.

### DDR delay-control logic comparison (2026-10-11)

`tools/compare_ddr_control_logic.py` reconstructs logical LUT cones from packed
INIT and original input mappings, stopping at named signal boundaries. A
canonical binary decision diagram compares all 342 CE/LD sink functions,
without sampling the CSR decoder address space: all match golden. The report
explicitly assumes candidate per-bank CSR address copies equal golden's shared
CSR address on the same cycle, and maps the respective CSR write-enable names.
The separate CSR replication simulation supports that design assumption, but
this audit does not prove its physical implementation or sequential behavior.
The BDD evaluator was checked against direct LUT evaluation for 1,260 input
assignments; inverting only DQ32 IDELAY CE produces one mismatch with a verified
counterexample. No original artifacts or hardware were changed.
Evidence: `evidence/zc706/integrated-20261011/ddr-control-logic-comparison.json`.
Next inspect the actual lane-select storage/CSR readback and sequential bitslip
control, since equivalent combinational control cones do not prove delivered
training pulses or correctly updated lane-select state on hardware.

### Physical DDR lane-select readback (2026-10-11)

`pl-ddr-test --diagnose-controls` saves/restores the PHY lane-select register,
tests all 256 byte values and 512 walking-one/walking-zero transitions per
lane. It performs 4,352 writes/readbacks without DDR initialization, pulse
writes, or DDR RAM access. Both integrated and golden images passed with
zero errors using identical software SHA-256
`6279f08a79c0733c04e17ac589f8124203313ae539bf38b412139099332b70ad`.
Thus a simple lane-select CSR read/write fault, including bit 4, was not observed.
This does not prove delivery of training pulses to PHY delays/bitslip counters.

Reproducer: build current DDR software against integrated generated headers,
then run `tools/test_ddr_reference_hardware.py --host <current-IP>
--diagnostic controls --software <new-pl-ddr-test> --output <new-directory>`.
The wrapper held the shared ZC706 lock throughout both volatile JTAG loads,
UART boots, SSH transfers/tests and restoration. No SD/QSPI writes. Golden
was restored and passed three complete 1-GiB BIST runs with zero errors;
current management address is 192.168.2.14. Evidence:
`control-readback-hardware-result.json`, both control logs and compressed
restored golden BIST log. Integrated DDR remains FAIL. Next compare lane-4
bitslip counter CE/reset/update and physical site mux configuration.

### Lane-four bitslip counter controls and FF encoding (2026-10-11)

`tools/compare_ddr_bitslip_controls.py` locates all 48 counter state FFs for
DQ32..39, write/read bitslip (two three-bit counters per DQ). Clock, CE and
set/reset combinational cones match golden at the previously documented
named-signal boundaries: 144 comparisons, zero mismatches. INIT, synchronous
mode and primitive type match. FASM ZINI/ZRST, FFSYNC, clock inversion and
CE/SR used-mux settings agree with each FF's packed configuration in both
images. Changing only DQ32 read-bitslip bit0 INIT in a fixture produces exactly
one missing required ZINI feature; original artifacts remain unchanged.
Evidence: `evidence/zc706/integrated-20261011/ddr-bitslip-controls.json`.
No hardware access occurred. This does not prove the D/arithmetic update path,
assembled configuration bits or physical pulse delivery. Integrated DDR still
fails byte 4; golden remains on 192.168.2.14. Next trace counter arithmetic and
the lane-4 data/strobe path, followed by a targeted physical experiment once
there is a discriminating hypothesis rather than another unchanged reload.

### Lane-four bitslip counter next-state logic (2026-10-11)

The packed-netlist logic reader now traverses CARRY4 sum/carry outputs and
excludes generated `$legal` net aliases from assumed named boundaries. A
1024-case exhaustive carry sum/carry test agrees with integer addition.
Byte-4 bitslip comparison now includes D as well as CK/CE/SR: 192 functions
match golden. Independently, all sixteen three-bit write/read counters
implement `(state + 1) mod 8` for every state in each image (128 checks per
image). Inverting just DQ32 read-counter bit0 next-state function is detected
as exactly one mismatch with a directly verified counterexample. The earlier
342 delay CE/LD comparisons still pass with this stricter alias handling.
Evidence: `evidence/zc706/integrated-20261011/ddr-bitslip-next-state.json`.
No hardware was accessed; golden remains restored at 192.168.2.14. These checks
prove logical combinational behavior at named signal boundaries, not timing
or physical delivery. Next prepare a raw DFI read-data diagnostic during
training to distinguish byte-4 sampling failure from write/strobe failure.

### Sampled raw DFI training data (2026-10-13)

`tools/build_ddr_software.py --trace-dfi` instruments a build-local copy of
liblitedram's existing pattern check. It logs expected/actual 16-byte DFI
phase data for module 4, first eight checks and every 128th check thereafter,
with a hard 256-row cap. Default builds still compile the original source.
`tools/analyze_ddr_dfi_trace.py` checks formatting and summarizes per-byte
values/errors; exact-match, isolated-bit-error and malformed-input fixtures pass.

A locked volatile-JTAG comparison used identical instrumented software on
candidate and golden. Candidate again failed training and showed 14,776 byte
errors only in lane 4; golden passed with all lanes clean. Candidate sampled
256 raw phase rows, byte 4 had 60 distinct values; golden sampled 232 rows,
byte 4 had 34 values. The candidate path is not frozen at 00/FF. Sampled
training mismatches are expected at deliberately untrained scan settings:
these counts do not establish whether write/strobe or read timing is faulty.
Golden was restored and passed three complete 1-GiB BIST runs. Current IP:
192.168.2.11. Shared ZC706 lock covered JTAG/UART/SSH/testing/restoration;
no SD/QSPI writes. Evidence: `evidence/zc706/integrated-20261013/`.
Next correlate byte-4 expected/actual bit sequences across phases and scan
settings, then select a targeted write-vs-read timing experiment.

### Raw byte-four burst correlation (2026-10-13)

`tools/correlate_ddr_dfi_trace.py` groups four phases into eight-beat bursts,
then tests all source lanes, cyclic beat shifts and inversion. Candidate has
64 complete bursts with zero exact fits; its best same-lane rotation still
has 11 bit errors. Even independent per-bit shift/inversion fits yield zero
exact bursts. Golden has 58 complete bursts, including nine exact same-lane
fits. These sampled settings include intentionally untrained states; this
is not proof of write-vs-read causality or an exhaustive hardware scan.
Synthetic rotated-byte, inverted substituted-lane and duplicate-rejection
checks pass. Evidence: `dfi-correlation-summary.json` and compressed full
correlation reports in `evidence/zc706/integrated-20261013/`.
No hardware access occurred. Next implement a bounded module-4 write-DQS
sweep together with read bitslip/delay scanning, using existing LiteDRAM
training helpers in a build-local diagnostic copy; compare with golden
under the shared board lock and restore the golden full BIST afterward.

### Physical byte-four DQS/read sweep (2026-10-13)

`tools/build_ddr_software.py --dqs-sweep` appends the diagnostic fragment
`software/pl_ddr/dqs_sweep.c.inc` to a build-local liblitedram copy. The new
`pl-ddr-test --sweep-dqs` option initializes with ordinary training, then
varies only module-4 write-DQS across 32 offsets, read bitslip across 8 offsets
and read delay across 32 taps. Write-DQ settings and other lanes are retained.
The scan has a 120-second deadline, switches back to hardware control on every
normal exit, and validates any one-seed match against all three training seeds.
Offsets are relative to the PHY reset settings, not absolute DQS tap numbers.
It is diagnostic only; modified delays require retraining/restoration afterward.

Under one shared ZC706 lock, candidate exhausted all 8192 combinations without
a passing setting; best single-seed result was 10 bit errors. Identical software
found a three-seed passing setting on golden after 65 tests (DQS reset offset 0,
read bitslip offset 2, read delay 0). Thus the scan detects a working window on
the reference, but a DQS-only adjustment does not repair the candidate failure.
Golden was reloaded and passed three complete 1-GiB BIST runs; current IP is
192.168.2.15. No SD/QSPI writes. Evidence: `dqs-sweep-hardware-result.json`,
`dqs-sweep-summary.json` and compressed logs in the 20261013 evidence directory.
Reproducer: `tools/test_ddr_reference_hardware.py --host <current-IP>
--diagnostic dqs-sweep --software <diagnostic-pl-ddr-test> --output <directory>`.
Next include write-DQ delay in the bounded sweep while retaining golden
comparison and restoration, since that dimension was explicitly held fixed.

### Physical byte-four write-DQ/DQS/read sweep (2026-10-13)

The diagnostic now accepts `--sweep-dq-dqs`: 32 write-DQ offsets × 32 write-DQS
offsets × 8 read bitslips × 32 read taps, still under a 120-second deadline.
The candidate exhausted all 262,144 combinations without a passing setting.
Best single-seed score was 7 bit errors at write-DQ offset 0, write-DQS offset
1, read bitslip offset 4, read delay 13. This is not a stable or passing setting.
Write bitslip and global timing were held fixed. Golden, with identical test
software, again found a three-seed passing setting after 65 tests.

Reproducer: build with `--dqs-sweep`, then run the locked comparison wrapper
with `--diagnostic dq-dqs-sweep`. The wrapper restored golden and its three
full-capacity BIST runs passed with zero errors; current IP is 192.168.2.18.
No SD/QSPI writes. Evidence: `dq-dqs-sweep-hardware-result.json`,
`dq-dqs-sweep-summary.json` and compressed logs in the 20261013 directory.
The measured binary's initial banner inherited the earlier "write-DQ retained"
text; actual progress records the full sweep. The banner was corrected afterward
and that cosmetic correction compiled successfully in a separate output directory.
Next capture per-DQ bit errors/raw DFI at the best scored configuration using
multiple seeds, to establish whether the residual failure is localized to a
particular data bit before choosing further timing or routing experiments.

### Per-DQ raw errors at the candidate's best sweep setting (2026-10-13)

Diagnostic builds now provide `--dq-detail`, measuring 16 repeats × 3 seeds ×
4 phases at write-DQ offset 0, write-DQS offset 1, read bitslip offset 4 and
read delay 13. `tools/analyze_ddr_dq_detail.py` counts each DQ's errors and
expected/actual ones. Parser fixtures verify an isolated DQ35 error and reject
malformed rows. Candidate produced 384 samples per DQ, with errors for DQ32..39:
`[0, 48, 16, 132, 0, 145, 0, 172]`. DQ32/36/38 match for all sampled seeds;
residual failure affects multiple other bits, rather than one stuck DQ.
Golden was intentionally forced to the same candidate-specific settings and
also failed that diagnostic; its counts do not invalidate golden qualification.
Golden was subsequently reloaded/retrained and passed three full-capacity BIST
runs. Current IP: 192.168.2.21. No SD/QSPI writes.

The first attempt reset PS and stopped at U-Boot, then openFPGALoader reported
USB interface claim failure. The original wrapper's restoration was blocked
by SSH sync to the stopped Linux. A separate locked golden JTAG recovery without
SSH dependency succeeded, including full BIST; no shared hw_server was stopped
or reconfigured. The claim failure did not recur during recovery or the retry.
Its owner/cause is unproven. The wrapper now omits SSH sync during restoration
when candidate boot did not complete and initializes restoration status to false.
The successful retry held the board lock for all boot/UART/SSH/tests/restoration.
Evidence: `dq-detail-*` files in the 20261013 directory.
Next compare physical sites and DDR clock branches for failing versus passing
DQ bits, and obtain a per-bit eye map to assess whether their timing windows
fail to overlap. Current fixed-setting counts do not establish write/read cause.

### Physical per-DQ read eyes expose incompatible beat alignment (2026-10-13)

Diagnostic `--dq-eye` fixes write-DQ offset 0/write-DQS offset 1 and scans all
8 read bitslips × 32 read taps. At each point it runs three seeds four times:
96 sampled bits per DQ. The build-local pattern hook accumulates per-bit errors;
`tools/analyze_ddr_dq_eye.py` requires all 256 distinct points and rejects
missing/duplicate data. Known-window and completeness fixtures pass.

Candidate has individual passing windows on every DQ, but no common setting:
DQ32/37/39 pass at bitslip offsets 2–3, while DQ33/34/35/36/38 pass at 4–5.
Golden has all eight DQ passing at 2–3 with 23 common zero-error settings.
This exposes incompatible beat alignment inside candidate byte 4 rather than
absence of a usable input eye on every bit. Finite sample windows remain
laboratory diagnostics, not full DDR qualification. Clock/reset alignment is
now a hypothesis; cause has not been proved. The passing/failing groups are
not simply the two halves of each physical I/O tile.

Both tests and golden restoration held the shared board lock. Golden reloaded
and passed three complete 1-GiB BIST runs; current IP 192.168.2.23. No SD/QSPI
writes. Evidence: `dq-eye-*` files in the 20261013 directory. The measured eye
mode did not update the older final `best_errors` field; use the per-point
counters/summary instead. That scalar logging omission was corrected afterward
and compiled separately. Next repeat PHY initialization/eye measurement within
one candidate load to determine whether the groups vary with reset release,
before changing physical clock/reset implementation.

### Reinitialization changes candidate per-DQ alignment (2026-10-13)

The locked comparison wrapper now supports bounded `--repeats 1..3`. Three
full PHY/JEDEC initialization and training runs followed by complete per-DQ
eye scans were performed within one candidate PL load, then three within one
golden load. This is not a reset-only experiment: write/read training repeats.

Candidate runs 1/3: DQ32–36/38 pass at bitslip 4–5, DQ37/39 at 2–3.
Candidate run 2: DQ35 additionally moves to 2–3. All runs have zero common
passing settings. Golden remains identical across all three runs: all eight
DQ at 2–3, with 23 common passing settings. Each scan contains 256 points,
96 samples per DQ per point. Thus alignment is not entirely fixed by the
placed/routed image; initialization/training state affects the failing design.
This supports investigating clock/reset/gearbox startup, but does not isolate
a read-side cause, a write-side cause, or a toolchain defect.

Golden restored and qualified with three full 1-GiB BIST passes, zero errors;
current Linux IP 192.168.2.25. Shared ZC706 lock covered all accesses and
restoration. No SD/QSPI writes. Evidence: `dq-eye-repeat-*` and `repeat-*`
in `evidence/zc706/integrated-20261013`. Next isolate reset-only behavior from
training and inspect ISERDES reset release relative to the DDR clock domains.

### Control: repeated scans without reset or retraining (2026-10-13)

New diagnostic `--dq-eye-no-retrain` runs three complete eye scans after one
initialization/training, with a shared 120-second deadline. Each scan resets
and sweeps byte-four software read bitslip/delays and normalizes write delays;
it does not reset the PHY/serializers or rerun training. Candidate passing
bitslip groups stay identical in all three scans: DQ32/35/36/37/39 at 2–3,
DQ33/34/38 at 4–5, zero common settings. Golden keeps every DQ at 2–3;
common passing setting counts are 22/23/23 (finite-sample boundary variation).
Thus scanning alone did not reproduce the group movement seen across full
initializations. Startup/training remains implicated; reset versus write
training and read versus write cause are still unresolved.

Source inspection shows `ddrphy_rst` also reloads command/DQ/DQS delays,
resets both software Bitslip directions, and resets OSERDESE2/ISERDESE2.
A bare reset cannot preserve the prior timing state. ISERDESE2 uses NETWORKING
DDR, CLK=DDR4x, CLKDIV=sys, BITSLIP=0; scanned read bitslip is fabric logic.
Next prepare a controlled build-local initialization variant that preserves
the command delay and explicitly normalizes write bitslip before comparing
reset-only effects; do not assume scanned bitslip directly controls ISERDES.

Shared lock held through candidate/golden tests and restoration. Golden full
three 1-GiB BIST passes have zero errors; Linux IP 192.168.2.27. No SD/QSPI
writes. Evidence: `dq-eye-no-retrain-*` and `no-retrain-*` in the 20261013
directory. Integrated DDR remains FAIL; ADC/PLL/SFP integration is not qualified.

### Reset/JEDEC reproduces movement without training (2026-10-13)

`--dq-eye-reset` performs an initial trained scan followed by two scans after
PHY reset, explicit command delay replay, JEDEC initialization and replay of
byte-four write bitslip. A build-local hook records the final write bitslip
selected by the upstream setter; invalid/unrecorded values abort replay.
Write DQ/DQS delays are normalized by each scan, read bitslip/delay swept.
No leveling search runs after either diagnostic reset. Other lanes are
untreated after reset, so this is strictly a byte-four diagnostic.

Candidate retained command offset 17/write bitslip 6. DQ35 changes from
passing at 4–5 in scans 1/2 to 2–3 in scan 3; other DQ groups remain unchanged.
All three have zero common settings. Golden has every DQ passing at 2–3
and exactly 23 common settings in all three scans. Therefore full retraining
is not necessary for group movement. Reset/JEDEC/startup remains implicated;
this does not distinguish read/write serializer startup, command effects,
or reset distribution from a clock-route/toolchain defect. No timing/pin
parameters were changed in PL. Next inspect reset fanout/routing and prepare
a controlled synchronized-reset candidate, retaining the current image.

Golden reloaded and passed three complete 1-GiB BIST runs, zero errors;
Linux IP 192.168.2.29. Shared board lock covered all accesses/restoration.
No SD/QSPI writes. Evidence: `dq-eye-reset-no-training-*` and
`reset-no-training-*` in the 20261013 directory. Integrated DDR remains FAIL.

### Experimental synchronized serializer reset build (2026-10-13)

Opt-in `--ddr-sync-reset` on the integrated target replaces RST on all 171
DDR ISERDESE2/OSERDESE2 instances with one shared two-FDPE synchronizer: async
assert from SYS reset or PHY CSR reset, deassert after two SYS rising edges.
Both registers use INIT=1, ASYNC_REG and DONT_TOUCH. Delay reload and fabric
Bitslip reset retain their original behavior. Upstream LiteDRAM is unchanged;
the experiment rewrites only this target's primitive inputs. Default target
behavior is unchanged. This is a hypothesis test, not a qualified fix.

RTL generation passed; all 171 serializer RST ports verified to share
`ddr_serdes_reset_sync`, with both FDPE stages present. Evidence:
`synchronized-reset-generation.json`. Full build started in isolated directory
`build/zc706-integrated-reset/gateware`, log
`build/zc706-integrated-reset-build.log`. Timing/bitstream and hardware tests
remain PENDING/NOT_RUN. Build command:

```sh
python3 tools/environment.py build/python/bin/python tools/build_pl.py \
  --board zc706 --design integrated --ddr-sync-reset --router router2 \
  --output-dir build/zc706-integrated-reset/gateware \
  --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys
```

No hardware accessed in this step. Board retains qualified golden at
192.168.2.29 from the preceding restoration. Next inspect completed setup/hold
results and reset routing before a locked candidate/golden comparison. A whole
design rebuild also changes placement/routing, so any improvement will require
further controls before attributing it exclusively to reset synchronization.

### Synchronized-reset first route rejected; second seed building (2026-10-13)

The first reset experiment route finishes but fails SYS setup: 82.67196 MHz
achieved versus 83.33334 MHz required. Final hold repair inserts 13 buffers
and reports zero remaining violations; earlier hold errors in the log precede
repair. The failing SYS path ends at a distant register CE through a large
logic/mux cone. Both reset synchronizer stages survive packing as SLICE_FFX.
No bitstream is qualified and no hardware programming was attempted.
Evidence: `synchronized-reset-seed1-route.json` and compressed stage1 log.

Added explicit `--seed` (default 1) to nextpnr invocation and recorded it in
the manifest. A second bounded trial uses seed 2 with identical RTL/clocks,
isolated output `build/zc706-integrated-reset-seed2/gateware`, log
`build/zc706-integrated-reset-seed2-build.log`; currently BUILDING. Existing
seed-1 artifacts and both original/golden bitstreams are preserved. This
placement trial is not a change in DDR electrical/timing parameters. Next
inspect the completed report; hardware comparison remains gated on clean
setup/hold and matching bitstream manifest. Board was not accessed this turn.

### Seed 2 reaches setup target but exhausts 6-GiB routing limit (2026-10-13)

Second seed reaches SYS 83.82 MHz (required 83.33) before final hold repair.
First repair adds 12 buffers with one violation remaining; next router2 pass
is killed by SIGKILL. Container cgroup memory.events shows oom=1/oom_kill=1
(max=68660). This is a resource failure, not a qualified timing result or
a demonstrated gateware defect. No manifest/qualified bitstream exists.
Evidence: `synchronized-reset-seed2-oom.json` and compressed stage1 log.

Host had 13 GiB available of 15 GiB; a bounded retry was started with 8 GiB
container memory, two CPUs and no swap. `tools/environment.py` now accepts
`KASLI_BUILD_MEMORY=6g|8g`, defaults to the existing 6g; invalid values reject.
Retry retains identical RTL and seed 2, isolated output
`build/zc706-integrated-reset-seed2-8g/gateware`, log
`build/zc706-integrated-reset-seed2-8g-build.log`. Prefix previous build
command with `KASLI_BUILD_MEMORY=8g` to reproduce. All prior artifacts kept.
No HW accessed; golden remains the last validated board image. Next inspect
retry completion, return container to default memory after the build, then
perform locked hardware tests only if setup/hold and manifest validate.

### Synchronized-reset candidate physically fails DDR (2026-10-13)

The 8-GiB seed-2 retry completed bitstream assembly with SYS 83.82 MHz and
zero final hold violations (13 buffers). SHA-256:
`bd66e49ac89e64d1690fb021b8bea12ea35e0a341767f0a9dd158c05c435d3a2`.
Container memory returned to default 6 GiB after completion.

Locked hardware test booted Linux and ran one trained eye scan plus two
PHY-reset/JEDEC/timing-replay scans. All three have DQ32–36/38 passing
at bitslip 4–5, DQ37/39 at 2–3, zero common settings. Shared two-stage
serializer reset release therefore does not fix byte-four alignment. No
movement occurred in these three scans, insufficient to establish whether
synchronization improves repeatability. Golden control has a common eye;
restored golden passes three complete 1-GiB BIST runs with zero errors.
Current Linux IP 192.168.2.10. No SD/QSPI writes; shared board lock held
through all transports, reset/programming and restoration.

Evidence: `sync-reset-*` files in the 20261013 directory. This experiment
remains optional and unqualified; original baseline is preserved. Next
compare routed SYS/DDR4x clock pin paths and emitted ILOGIC clock polarity
for DQ37/39 versus the other six bits, using golden as the control. Reset
release alone is no longer a sufficient repair hypothesis.
