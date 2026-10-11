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
