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
