# Qualified ZC706 integrated fixed-Yosys build

Physical qualification 2026-10-22: ZC706 rev1.2, XC7Z045FFG900-2,
two FMC ADC100M4cha v6.1, independent100MHz ADC clocks, PL SODIMM,
WR-derived dual PLL and external FS SFP-GE-T through the Netgear switch.
This is a PL diagnostic bundle, **not an SD image**. Existing SD Linux boots
both Cortex-A9 cores. Kasli-SoC hardware qualification remains pending.

Bitstream SHA256:
`3d050ef1cb859bb494df726d328a75059423bdb792f519036ecae533feccde6e`.

## Results and limits

- SYS85.11/83.333MHz, ADC1 120.35/100MHz, ADC2 103.80/100MHz; setup/hold PASS.
- All35 static SRL16E covered by experimental SDF-derived timing model.
- DDR init/leveling, GP1 address test and three whole1GiB BIST passes PASS.
- Dual independent ADC sequence/pattern/rearm,4194304samples/card, no errors/drops.
- Concurrent dual PLL:21787phase records/card,std1.712/1.704ns.
- External switch:20/20ICMP,350/350byte-exactUDP,157300bytes; no new MAC/clock errors.
- Golden restored and three whole1GiB BIST passes PASS, final DHCP192.168.2.18.
- Internal PMA loopback NOT_RUN. Continuous streaming and deterministic sample
  alignment are not qualified. No SD/QSPI/OTP writes were performed.

## Build

Use the repository environment and pinned `sources.lock.json` and
`toolchains.lock.json`. This qualification used the installed/cached environment,
not a clean cache-free replay. No Vivado was used. Yosys from pinned OSS CAD
Suite20261005 is0.69+190 (`0e8336b4e`); the older0.52 drops SRL clock enables.

On the shared build host, following `docs/toolchains/heavy-builds-remote-handoff.md`
in the parent workspace:

```sh
dell-build sync kasli-linux
dell-build run kasli-linux timeout 3600 build/python/bin/python tools/build_pl.py \
  --board zc706 --design integrated --ddr-sync-reset --no-header-probes \
  --srl-timing --seed 3 --router router2 \
  --prerouted evidence/zc706/integrated-20261013/golden-mmcm-native-prerouted.txt \
  --output-dir build/zc706-integrated-yosys-fixed-cdc-ready/gateware \
  --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys
```

The integrated backend composes existing clock/hold fixes and isolated static
SRL timing. Alias-only techmap preserves DDR inouts. ADC CDC/output/command
queues, registered-ready cut, buffered bank commands, and a scoped optional
AXI beat pipeline close the observed paths. The LiteX checkout stays unchanged:
`gateware/axi_beat_pipeline.py` applies the pinned patch to a temporary module.
Its11 upstream AXI regressions and dual-clock ADC simulation passed.

## Physical test

Keep the documented shared board lease across programming, UART, SSH, tests
and restoration. Use the wrapper; do not run child hardware tools separately.
Actual management DHCP may change on reset.

```sh
python3 tools/test_integrated_hardware.py \
  --host ACTUAL_IP --work-dir build/zc706-integrated-yosys-fixed-cdc-ready \
  --output /tmp/zc706-cdc-ready-hardware --program --external-network
```

Qualified `pl-ddr-test`, `adc-ddr-read`, `i2c.so` match236CSR registers,
memory maps and existing constants. Only `axi_beat_buffered=1` is added.
Hashes are retained in the physical validation evidence. Evidence is under
`evidence/zc706/integrated-fixed-cdc-20261022`.

## Package

```sh
python3 tools/package_integrated.py \
  --work-dir build/zc706-integrated-yosys-fixed-cdc-ready \
  --evidence-dir evidence/zc706/integrated-fixed-cdc-20261022 \
  --validation evidence/zc706/integrated-fixed-cdc-20261022/validation.json \
  --readme docs/zc706-integrated-fixed-yosys.md \
  --output /home/codex-hil/artifacts/zc706-fixed-cdc/zc706-integrated-fixed-yosys.tar.xz
```

The packager rejects mismatched bitstreams/software or absent core/restoration
proof and emits SHA256SUMS. Preserve the earlier qualified no-SRL bundle.

## Clean-checkout audit

Run the read-only inventory without hardware access:

```sh
python3 tools/audit_integrated_bootstrap.py \
  --output /tmp/zc706-bootstrap-audit.json
```

The2026-10-22 audit confirms27/27 source revisions match the lock file.
The backend cache paths have generators: baseline nextpnr is built by
`ddr_nextpnr.py`; ADC, hold, GTX, integrated and SRL layers call their base
preparers before relinking. Chipdb and WR HDL also have generators.
Their presence in the qualified cache is not itself a clean-replay result.

The isolated source/object-cache replay described below completed successfully.
The environment bootstrap pins a dated Debian snapshot (20261005T000000Z)
as well as the base image digest. Exact installed versions are captured in
`evidence/zc706/clean-replay-20261022/runtime-versions.txt`. They describe the
reused Dell runtime, not a freshly installed runtime validation.

Replay preparation2026-10-22: Dell has186GiB free. A Git archive snapshot
was expanded into `build/clean-replay-a903dc6`; ten required PL source
repositories were cloned from pinned source-only Git bundles. The nextpnr
metadata gitlink was verified. No generated objects or chipdb were copied.
All six Python source libraries resolve inside the isolated tree. Only the
existing runtime/interpreter and pinned tool asset cache are reused.
The first preparation exposed absent Git metadata in some migrated source
copies; source bundles resolve this without changing those copies.
Full isolated replay completed with seed3/router2 and the qualified clock
settings. Preparation provenance:
`evidence/zc706/clean-replay-20261022/preparation.json` and `source-bundles.json`.
The standalone preparer is `tools/prepare_clean_replay.py`; it refuses an
existing destination and verifies source revisions/tool archive markers.

Final isolated replay: **PASS** (process exit0). Fresh nextpnr objects, chipdb,
Yosys synthesis, routing and bitstream assembly completed without Vivado.
Setup/final hold passed; SYS85.106MHz, ADC1 120.351MHz, ADC2 103.799MHz.
`top.frames` is byte-identical to the physically qualified build. The complete
13,321,404-byte configuration payload is also identical, SHA256
`29a86b08b362d2f5c764a159eead390a93aaf4afd61dc7f17f73fda097d39d35`.
Only the `.bit` header time differs (16:29:55 versus14:33:11); full file SHA256
is therefore different. This is an offline reproduction, not a new hardware run.
The replay still reuses the existing runtime/interpreter and pinned tool assets;
it does not yet prove fresh OS/package/tool installation from the network.
Evidence: clean-replay `manifest.json`, `timing.json`, `comparison.json`,
`payload.json`. Next record runtime/compiler versions and close bootstrap
installation documentation; preserve the qualified bundle unchanged.

## Installation and one-command PL build

On a separate build machine with Docker, `make bootstrap BOARD=zc706` creates
its project-local environment, fetches locked sources and verifies tool archive
SHA256 values. This downloads all source entries, including optional projects.
Do not run that Docker environment bootstrap inside the shared Dell runtime.
After bootstrap, `make integrated-fixed-pl` builds this configuration.
For the prepared shared Dell environment use:

```sh
dell-build sync kasli-linux
dell-build run kasli-linux make integrated-fixed-pl ENV=
```

`ENV=` selects the already prepared runtime instead of nesting Docker. The
legacy `integrated-pl`/`integrated-qualified-pl` targets retain their historical
settings; use `integrated-fixed-pl` for the fixed-Yosys configuration. Override
`INTEGRATED_FIXED_DIR` to retain separate trials. The isolated replay has
validated source-to-configuration reproduction; a newly downloaded and installed
runtime/toolchain has **not** yet been tested. The snapshot repository and tool
release URLs remain external availability dependencies. Installed system Yosys
0.52 is listed in the inventory but is not used by this target.

Fresh archive installation can be tested independently of source compilation:
place the two release archives (URLs and SHA256 in `toolchains.lock.json`) in
an input directory as `openxc7.tgz` and `oss-cad-suite.tgz`, then run inside
the build runtime:

```sh
python3 tools/install_tool_assets.py --archives INPUT_DIR --destination NEW_TOOLS_DIR
```

The installer refuses an existing destination and verifies both archive hashes
before extraction. It retains any failed extraction for diagnosis. Its manifest
means extraction only; run the tools and a build before declaring installation
qualified. This procedure leaves `build/tools` and the qualified bundle intact.
Fresh download/extraction trial on Dell completed for both locked archives in
`build/fresh-tool-download-20261022` and `build/fresh-tools-20261022`.
Fresh Yosys plus fresh Icarus passed both clock-enable regressions (SRL enabled
and disabled). Fresh openXC7 assembly from the qualified FASM/database passed; generated
frames are byte-identical (SHA256 `27205eb789dce8e66be92782db5dd91e2dfac6526358d0b2fb2435e877595a1b`). This is tool installation/execution coverage, not a fresh
OS installation or a second full synthesis/routing run. Evidence is under
`evidence/zc706/fresh-tools-20261022`.

## Fresh OS installation trial

`python3 tools/environment.py --write-containerfile Containerfile` renders the
same pinned base image, dated Debian snapshot and package list without starting
Docker or changing the existing environment. On a dedicated build host use
`podman build --no-cache -t zc706-runtime -f Containerfile EMPTY_CONTEXT_DIR`.
On the shared Dell take the documented shared build lease for this provisioning
operation; no project/runtime/device mounts are needed. Network is required only
for fetching the snapshot packages. The normal FPGA build runtime stays offline.

The2026-10-22 isolated OS installation completed successfully, image ID
`2e0a9a1e2c7a005345c56340a9e83a18c9c8e84c362f86ecadb1d750464a295f`.
A new virtualenv installed all eight locked external Python dependencies.
Ten source repositories and the nextpnr metadata were prepared from pinned Git
objects; all six source imports resolve inside the new tree. The preparation
report uses generic wording about reused tools/runtime; in this trial the runtime
and Python are freshly installed, and the new tree's `build/tools` symlink was
explicitly switched to the freshly downloaded/extracted tool installation.

A full synthesis/routing/assembly trial completed offline in that fresh
image (exit0) with a7200-second bound and shared build lease. It has no migrated runtime
mounts, no hardware access and no copied generated objects/chipdb. The previous
project is mounted read-only as a source/asset cache. New outputs stay under
`build/fresh-runtime-trial-20261022`. Setup/final hold passed; frames and the complete BIT configuration payload
are byte-identical to the physically qualified build. Only the BIT header time
differs. This is an offline reproduction, not another hardware test. Recipe, package inventory, Python install log and preparation
provenance are in `evidence/zc706/fresh-runtime-20261022`. Existing runtime tags,
qualified bundles and hardware configuration remain unchanged.

Fresh-runtime build progress: backend compilation, chipdb generation and Yosys
synthesis completed. nextpnr is refining placement. Generated XDC is identical
to the earlier isolated replay; generated Verilog is identical after removing
comments (quoted strings preserved). Differences are generated timestamps and
hierarchy comment ordering. This comparison is not final routing/timing proof.
See `fresh-runtime-20261022/synthesis-comparison.json`.

Final fresh-runtime result: **PASS**. SYS85.106/83.333MHz,
ADC1 120.351/100MHz and ADC2 103.799/100MHz. Configuration payload SHA256
`29a86b08b362d2f5c764a159eead390a93aaf4afd61dc7f17f73fda097d39d35`.
Evidence: `fresh-runtime-20261022/comparison.json`, `manifest.json`,
`timing.json`, `status.json` and compressed full build log. This closes the
fresh OS/Python/tool installation and source-to-bitstream replay trial. Pinned
source Git objects were reused; network re-download of every upstream source
was not part of this trial. Existing hardware qualification and archive stay
unchanged. Continuous ADC streaming, deterministic alignment and Kasli-SoC
hardware qualification retain their separate pending status.

## Internal loopback follow-up (2026-10-22)

A bounded physical run of the same qualified bitstream passed Linux boot and
three whole1GiB DDR BIST passes. Near-end PMA loopback acquired GTX/PCS status127,
with measured TX/RX approximately125MHz and zero clock faults. Packet0 was not
received: TX1, test RX0, MAC RX211, CRC1 and preamble185 at failure. Internal
loopback is **FAIL**, not a successful packet test. The wrapper restored the
golden image and repeated three whole1GiB DDR BIST passes; lease release was
verified. Final management DHCP is recorded in the validation report.
No SD/QSPI/boot-environment writes. External switch qualification remains the
separate earlier PASS. Evidence: `evidence/zc706/integrated-internal-20261022`.
Next compare the loopback control and packet path with the earlier successful
internal diagnostic before changing GTX configuration or drawing a HW conclusion.

Internal PMA control comparison: all GTXE2_CHANNEL parameters and captured DRP
registers match the2026-10-14 successful build. Loading that exact old build
again with the current copper SFP also fails packet0 (status127, TX1/testRX0,
CRC1/preamble353). This does not isolate a new synthesis/routing regression.
The historical test had no readable module EEPROM; that alone does not prove
its cage was empty. Golden restoration and three whole1GiB BIST passes PASS;
shared lease release verified. Evidence: `internal-control-20261022`.
A new `--internal-loopback-only --program` wrapper mode bounds packet diagnostics
without retraining ADCs/running PLLs, while retaining golden+BIST restoration.
Next separate GTX near-end PCS versus PMA modes under the same conditions,
then inspect framing/polarity/reset only where the comparison supplies evidence.

## PCS versus PMA experiment

[AMD UG476](https://docs.amd.com/v/u/en-US/ug476_7Series_Transceivers), Loopback,
requires RXBUF enabled and RX_XCLK_SEL=RXREC for near-end PCS. With PMA-selected
RXOUTCLK, select PCS clock output or assert RXCDRHOLD. Existing netlist uses
RXBUF=TRUE/RXREC/RXOUTCLKSEL=010 and fixed RXCDRHOLD=0, so switching only the
LOOPBACK port to001 is not admitted as a valid PCS comparison.

Separate diagnostic build `zc706-integrated-pcs-hold-20261022` sets RXCDRHOLD
only when synchronized LOOPBACK=001. PMA010 and external000 retain hold0.
`--internal-loopback-only --internal-loopback-mode pcs --program` selects the
bounded test with golden restoration; default remains PMA. Before hardware,
PCS admission checks the synthesized RX buffer/XCLK/OUTCLK and rejects a fixed
CDR-hold input. Old artifact rejection and Python syntax checks passed. Dynamic
hold truth-table/routed-path verification, timing and physical PCS/PMA tests
remain pending. A new build is running on Dell; no hardware was accessed.
Evidence: `evidence/zc706/pcs-hold-20261022`.

PCS logical admission: `tools/check_gtx_loopback.py TOP_JSON` verifies the
synthesized GTX buffer/clock conditions and exhaustively evaluates the direct
LUT3 CDR decoder for all eight LOOPBACK values. Actual synthesized netlist PASS:
hold1 only for001, hold0 otherwise. One positive fixture and all eight individual
truth-table bit corruptions behaved as expected; incorrect functions are rejected.
The wrapper now uses this check rather than accepting any dynamic hold signal.
This is logical admission only; final routing/timing and hardware remain pending.

PCS integrated trial was rejected: nextpnr exit1, SYS82.45/83.33MHz, final
hold clean. Worst SYS path is BRAM `storage_29.0.0/DOADO8` to
`storage_29.0.7/ENARDEN` (12.128ns), including a3.819ns route into BRAM enable.
No candidate bitstream was admitted or programmed. Preserve this failed route.
To isolate PCS/PMA behavior without DDR timing pressure, a separate SFP-only
build is running with the same CDR-hold change, FCLK reference, SRL timing model,
seed3/router2 and pinned fixed Yosys. Existing integrated golden stays unchanged.
Its output is `build/zc706-sfp-pcs-hold-20261022/gateware`.

Isolated PCS build completed: setup/hold PASS, bit SHA256
`bab3fb2885d4a91860020f6b3e1fca334adda59fb7f0fddf84e9ea6f4598af25`.
Packed original-pin connectivity and all eight CDR decoder cases PASS; this
checks netlist metadata, not independent bit-level routing equivalence.
Physical PCS packet test FAIL: status127, control9, clocks nominal125MHz,
TX1/testRX0, MAC RX161, CRC1/preamble1 at timeout. These are accumulated counters,
not a settled delta measurement; do not infer all MAC RX frames were looped data.
Golden restored and three whole1GiB DDR BIST passes PASS; lease reacquisition
verified. Evidence `pcs-hold-20261022/hardware`. No SD/QSPI/bootenv writes.
Next audit physical LOOPBACK pin mapping and test-frame receive filtering;
PCS failure alone does not identify a hardware or toolchain fault.

Loopback path audit: pinned GTX site metadata maps LOOPBACK0/1/2 and RXCDRHOLD
as identity-named input wires; no index reversal was found in that metadata.
This is not independent FASM/PIP or silicon routing proof. MAC crossbar dispatch
selects EtherType0x88b5 for PacketTest, independently of ARP/UDP users.
`test_sfp_logic.py` now also instantiates the production-size UDP/IP core with
ARP/ICMP and UDP echo before adding PacketTest. The existing generator/error
and standalone MAC byte-loopback tests passed on Dell. Full-core simulation
is still running with a240-second bound. It models MAC/CRC/CDC byte traffic,
not PCS symbols or analog GTX. No hardware accessed during this audit.
Evidence: `loopback-path-20261022`.

Full UDP/IP core loopback simulation finished **PASS**, including all three
numbered64-byte packets through the MAC/CRC/CDC path with ARP/ICMP/UDP users.
This does not model PCS symbols/GTX or prove the synthesized hardware behaves
identically. The next diagnostic adds passive TX/RX `MACFrameSnapshot` observers
under `header_probes`: arm explicitly, ignore fragments until next first beat,
freeze the first complete frame's EtherType, split32 source/destination MAC,
payload length and error. Counters are observed at packetizer input/depacketizer
output, before MAC crossbar receive filtering. MMIO can read the frozen result.
Rearm/fragment rejection/length/error/freeze simulation PASS. The loopback probe
arms observers before starting packet transmission, when those CSRs are present.
Separate SFP build `zc706-sfp-frame-capture-20261022` is running, with header
probes enabled. No timing admission or hardware result yet; golden unchanged.
Evidence: `loopback-path-20261022/fullcore-simulation.log`, snapshot simulation
and status. No hardware access in this step.

TX/RX frame observer validation in the full UDP/IP core completed **PASS** for
three packets with explicit rearm: both captures valid, EtherType88b5,64bytes,
error0. Physical capture recorded correct TX fields but no complete RX frame
at the depacketizer output after arming. Do not interpret accumulated MAC RX
counts as traffic during this capture. The probe now preserves a pre-transmit
counter snapshot and modulo32 deltas even when packet reception times out;
this software change has not yet been run on hardware.
Route-endpoint audit found LOOPBACK0/1/2 and RXCDRHOLD each routed to its
expected GTX sitewire in serialized nextpnr output. This still is not independent
FASM/bit equivalence. Evidence: frame-capture fullcore simulation and
`control-route-endpoints.json`. No hardware accessed during this follow-up.
Next measure settled TX/RX/CRC/preamble deltas with the same qualified diagnostic,
then use those results to place any additional raw PHY/PCS observation points.

PCS settled-attempt counter measurement: same timing-clean diagnostic image,
updated software retained the before/after counters. One TX test frame produced
MAC TX+1, MAC RX+1, CRC errors+1, preamble errors+0 and clock faults+0; PacketTest
RX stayed0. Correct frozen TX header/64-byte payload remains confirmed. This
shows a frame reaches the MAC core receive path during the attempt and fails
CRC; it does not prove its payload/header bytes match the transmission.
The observer sits after the MAC core/depacketizer and cannot describe bytes
discarded or marked invalid upstream. Next compare raw transmitted/received
frame bytes around CRC/preamble processing, including actual FCS and frame
length, before changing transceiver parameters. Simulation of the digital
MAC path already passes. Golden restored, three whole1GiB DDR BIST passes
PASS and shared lease release verified; final management DHCP192.168.2.18.
No SD/QSPI/boot-environment writes. Evidence: `frame-deltas-20261022`.

## Raw MAC/PHY byte capture diagnostic

`PHYFrameCapture` passively observes accepted PHY bytes in eth_tx/eth_rx,
uses existing LiteX depth256 CDC to sys, and freezes the first complete frame
in a128-byte Migen memory. It does not drive PHY ready/valid. Software arming
crosses via the upstream PulseSynchronizer; an in-flight frame is skipped.
CSRs expose done, actual received length, error/overflow flags, capacity and
byte-addressed frozen data. Frames larger than128 bytes are explicitly truncated;
overflow or incomplete capture cannot be used for FCS validation.
The software probe arms both raw captures, waits for domain acknowledgment,
and reads bounded data even on loopback timeout. This remains diagnostic only.

Async125→50MHz simulation PASS: fragments, rearm,90-byte frame, error flags and
160-byte truncation to the first128bytes. An initial testbench rearm race read
old done before its reset edge; corrected test waits that edge, with original
failure retained. Full-core simulation comparing raw TX/RX bytes,90-byte length,
preamble and independent Python CRC32/FCS is running on Dell. No new FPGA build
or hardware test is admitted until that comparison passes. Evidence:
`evidence/zc706/raw-capture-20261022`.

Full-core raw capture simulation completed **PASS**: three90-byte TX/RX frames
identical, seven55 preamble bytes plusD5, and actual FCS matched Python CRC32
in little-endian Ethernet byte order. This validates the diagnostic in the
byte-level digital model, not the PCS/analog transceiver or mapped hardware.
A separate SFP raw-capture build is now running on Dell:
`build/zc706-sfp-raw-capture-20261023/gateware`.

`tools/compare_phy_frames.py PROBE_JSON` decodes bounded captures, independently
checks preamble/FCS and test-frame bytes, and lists differing offsets. It refuses
complete-frame conclusions for missing done, overflow, truncation or inconsistent
length. Offline controls PASS: valid reference, four byte corruptions and four
incomplete/overflow cases. These are synthetic controls, not hardware data.
No hardware was accessed in this step; next collect build timing/admission and
perform a bounded raw-byte PCS capture with golden restoration.

## Physical raw-frame result (2026-10-23)

The raw SFP diagnostic passed timing/hold and was loaded under the shared lease.
TX and RX captures both completed:90bytes, no capture error/overflow, identical
byte for byte to the expected test frame. Both have valid preamble, correct
MAC/EtherType/payload and FCS `77b3d256`, independently checked with Python CRC32.
Nevertheless PacketTest packet0 timed out and the MAC CRC counter incremented.
This is a **raw boundary loopback PASS / downstream MAC packet FAIL**, not a
complete Ethernet qualification. It points the next investigation into the MAC
RX pipeline after the observed PHY boundary; no new evidence of serial-link
byte corruption was found in this captured frame. Next snapshot the CRC checker
input/output and upstream RX CDC/preamble stages, preserving the same test frame.
Golden restored and three whole1GiB DDR BIST passes PASS, lock release verified.
Final management address is in `raw-hardware-20261023/validation.json`.
No SD/QSPI/bootenv writes. Exact raw bytes and comparison are retained in that
same evidence directory; no additional packet was sent after restoration.

CRC-stage diagnostic preparation: passive captures observe the RX preamble
checker sink (after RX CDC), the real CRC input at `checker.fifo.sink` behind
BufferizeEndpoints, and the CRC checker source. Expected test lengths are90,
82 and78bytes respectively. Exact stage-byte assertions and capture validity
checks are running in the full-core digital simulation on Dell; no hardware
or new FPGA build in this step.
`compare_mac_crc_stages.py PROBE_JSON` compares these stages independently of
the error flag and recomputes FCS at the actual CRC input. Synthetic decoder
controls passed: valid chain, three stage corruptions, four incomplete captures
and an error flag with unchanged valid bytes. Evidence: `crc-stages-20261023`.

CRC-stage full-core simulation completed **PASS**: all three frames produced
exact90/82/78byte arrays at the respective boundaries, with done asserted and
no errors or overflows. Separate SFP diagnostic build is running on Dell in
`build/zc706-sfp-crc-stages-20261023/gateware`; no timing or hardware result yet.
This is a digital-model validation of the observation points, not proof of the
mapped FPGA CRC pipeline. Evidence: `crc-stages-20261023/fullcore-simulation.log`
and status. Existing qualified images and golden hardware remain unchanged.

CRC-stage physical attempt: raw TX/RX remained complete and valid, but all
three intermediate captures stayed armed with done0/length0. Decoder correctly
reports INCOMPLETE_STAGE_CAPTURE; this cannot localize byte corruption yet.
A possible cause is conservative in-flight-fragment rejection skipping the
first post-arm frame; this is a hypothesis, not a finding. Golden restoration
and three whole1GiB DDR BIST passes PASS; lock release verified.

The next software-only diagnostic can send3 identical frames, waiting for TX
completion rather than requiring RX before the next transmission. It still
fails if RX count does not match. `--internal-probe-burst 3` is restricted to
`--internal-loopback-only` and retains golden restoration. Mock control PASS:
three frames transmitted despite missing RX, final RX timeout still FAIL.
Hardware burst has not yet run. Evidence: `crc-stage-hardware-20261023`.

Three-frame physical burst: TX3, MAC RX3, PacketTest RX2, test errors0 and one
new CRC error. All intermediate observers now completed with correct90/82/78
bytes and valid FCS at the CRC input. Frames were identical; captures can be
from different ordinals and do not capture/prove the first failing frame's data.
This supports a mode-transition/startup-state hypothesis rather than continuous
corruption. The strict3/3 test remains FAIL. Golden restored and three whole1GiB
DDR BIST passes PASS; shared lease release verified.

An explicit `--internal-probe-warmup 3` diagnostic is prepared to record startup
frames separately, then strictly test1000 subsequent frames with unchanged
error/count checks. Default cold test stays unchanged. This is a settled-mode
experiment, not a fix for first-packet loss; that remains a known issue until
reset/flush behavior is understood. A mock control retains the initial dropped
frame in warmup and checks subsequent frame counts separately. Hardware warmup
has not run. Evidence: `crc-burst-20261023`.

## Settled near-end PCS qualification (2026-10-23)

Same isolated diagnostic bitstream, explicit3-frame warmup: warmup TX3/RX2,
CRC+1. Then **1000/1000 PCS packets PASS**, with MAC/test TX and RX each+1000,
no new CRC/preamble/clock/test-data errors. Raw TX/RX bytes and the90/82/78byte
RX-stage captures all match expected test data and independent FCS. Warmup
counters are retained separately; the first-packet loss remains unresolved.
This qualifies settled PCS operation only, not cold mode transitions, PMA or
ADC/DDR integration. Default cold diagnostic has not been weakened.
Golden restored; three whole1GiB DDR BIST passes PASS, shared lease release
verified. Evidence: `pcs-settled-20261023`. No SD/QSPI/bootenv writes.
Next compare settled near-end PMA with the same bitstream and explicit warmup,
then investigate coherent RX reset/flush during mode transitions.

Settled near-end PMA comparison also **PASS1000/1000**, same isolated bitstream,
explicit3-frame warmup retained TX3/RX2/CRC+1 separately. Qualification MAC/test
TX/RX each+1000 and CRC/preamble/clock/test errors each+0. Raw TX/RX and RX
90/82/78stage bytes match expected data, with valid independent FCS. Thus both
PCS and PMA work in settled mode. The cold first-frame loss after mode change
remains unresolved; these tests do not claim it fixed. Golden restored and
three whole1GiB DDR BIST passes PASS; lock release verified. Evidence:
`pma-settled-20261023`. No SD/QSPI/bootenv writes.
Next reproduce an interrupted RX frame/domain reset in the digital model,
checking RX CDC pointer reset and sys-domain preamble/CRC state, before choosing
any reset/flush implementation. Upstream CDC offers common-reset support but
its applicability here remains to be tested; do not assume a patch is proven.

## Interrupted RX frame simulation (2026-10-23)

Actual MAC/store-and-forward/2048-entry CDC RTL at 50/125 MHz reproduces the
startup counter pattern when a 12-byte frame prefix has no final beat: first
complete packet lost, CRC+1, next two packets accepted. With RX-domain reset
between prefix and packets, all three pass with zero CRC errors; sys continues.
Both no-prefix controls also pass3/3. Whole-matrix simulation timed out after
three completed cases; the reset-after-prefix case completed separately.
Evidence and bounded reproducer: `evidence/zc706/rx-reset-model-20261023`.
This supports an interrupted-frame hypothesis but does not identify the physical
cause or prove a reset patch necessary. K7 RX MMCM already resets via CDR lock
sequencing; next trace domain reset coverage and post-reset RX traffic. No new
hardware access or production gateware changes in this experiment.

PCS boundary follow-up: actual PCSTX->PCSRX RTL with a200-cycle decoder CE gap
while TX continues terminates the interrupted packet with last/error (14bytes
in this model), then accepts both following90-byte packets. Clean control is
three90-byte packets without errors. Both final regression assertions PASS.
Evidence: `evidence/zc706/pcs-boundary-model-20261023`. Thus a CE gap alone does
not explain an unterminated fragment; previous artificial-prefix result remains
a possible mechanism, not the diagnosed physical cause. Next observe RX startup
before the mode/reset sequence; no production reset patch or hardware change.

Early sys-domain capture physical run (same diagnostic bit, no warmup): first
packet still FAIL, CRC+1 only when it is sent. Startup itself changes MAC RX159
->168 and preamble0->2, CRC stays0; test packet then MAC RX+1/test RX0/CRC+1.
PHY TX/RX remain identical90-byte correct frames. Earlier sys snapshots caught
preceding external traffic and are truncated/independent, so cannot identify
the failed packet or prove cross-stage corruption. Evidence:
`evidence/zc706/startup-capture-20261023`. New opt-in probe ordering has three
offline tests PASS. Golden restored, three whole1GiB DDR BIST passes PASS;
shared lease released and verified. Final management DHCP192.168.2.18.
Next isolate post-reset capture or implement bounded valid/last/reset boundary
trace with frame ordinals. Default cold test remains unchanged; no reset fix.

Reset-held capture follow-up: sys probes armed after software PHY-reset assertion
and10ms wait, before release. Still captured preceding external traffic rather
than the test packet (231/399/395byte snapshots, truncated128; CRC output error1).
Independent frame ordinals unknown; no cross-stage corruption claim. Strict
first test packet again MAC RX+1/test RX0/CRC+1, PHY TX/RX correct90bytes.
Evidence `evidence/zc706/reset-held-capture-20261023`. Four offline ordering
checks PASS. Golden restored, three whole1GiB DDR BIST passes PASS, lease release
verified. Next model queued RX CDC traffic with write-domain-only reset while
sys read state remains alive; prior prefix model did not cover that case.

Queued CDC reset model: actual upstream unbuffered depth32 RX->sys FIFO,
125/50MHz, old data partially read and consumer paused. Reset of RX/write side
alone produces an invalid stream with repeated new data; upstream common reset
of both FIFO sides flushes old data and delivers exactly three new bytes with
correct final last. Clean/no-reset control also passes. Functional ideal reset
lowering only; no synchronizer timing/metastability/GTX proof. Evidence and
reproducer: `evidence/zc706/cdc-queued-reset-20261023`. This establishes a concrete
reset-coherency failure mechanism, not yet the physical root cause. Next test
full MAC downstream state: common FIFO reset alone may leave partial CRC/
preamble state in sys. No production reset change or hardware access yet.

Full MAC queued-frame model: complete90-byte frame committed, RX reset requested
when12 bytes reached sys preamble stage, RX FIFO uses common reset but sys MAC
parser stays active. First subsequent packet lost with CRC1, next two pass.
Final explicit valid-byte injection and counter assertions PASS. Thus common
FIFO reset alone is insufficient for a partly processed sys-domain frame.
Evidence: `evidence/zc706/mac-queued-reset-20261023`; upstream/production logic
unchanged. Physical cause still unproven. Next test coherent FIFO reset plus
MAC parser recovery at multiple frame positions before selecting a fix.

Model recovery PASS at12-byte header and40-byte payload positions: common RX
FIFO reset plus reset of whole MAC sys state and diagnostic packet consumer
receives all three new packets from the first attempt, CRC/preamble/data errors0.
Both bounded runs exit0; evidence `evidence/zc706/mac-recovery-model-20261023`.
This contrasts with common-FIFO-only reset, which lost the first new packet.
Test-only ResetInserter does not assert global sys reset or automatically reset
TX FIFO local aliases; no TX was active. Active-TX and full UDP/IP recovery remain
unqualified. No upstream/production gateware change, build or hardware access.
Next prepare opt-in SFP recovery with explicit FIFO reset ownership and protocol
state reset, then validate RTL and timing before any physical program operation.

Optional isolated SFP reset candidate implemented without upstream edits:
private net_sys/net_eth_tx/net_eth_rx domains use parent clocks, shared reset
assertion and per-domain synchronized release. Entire UDP/IP core, diagnostic
consumer and echo FIFO share reset; both FIFO endpoints are covered. PHY and
unrelated sys/CSR/status remain outside. --sfp-network-reset is isolated-SFP-only,
default off and recorded in manifest/CSR constant. Actual helper RTL model at
40bytes PASS: new packets3/3, CRC/preamble/data errors0. Evidence/reproducer:
`evidence/zc706/network-reset-candidate-20261023`. Build launched on Dell to
`build/zc706-sfp-network-reset-20261023/gateware`, elaboration completed, timing
and physical test pending. No hardware access or golden/integrated changes.

Whole-network reset candidate build PASS: setup/hold, net_sys71.235/50MHz,
RX167.308/125MHz, TX160.128/125MHz. Bit bda5b406...c63a0. Physical cold PMA
**1000/1000 PASS with no warmup**, first packet included; MAC/test TX/RX+1000,
CRC/preamble/clock/data errors+0. Raw TX/RX valid FCS, RX90/82/78stages match.
Evidence `network-reset-build-20261023` and `network-reset-cold-pma-20261023`.
Golden restored, three whole1GiB DDR BIST passes PASS, lease release verified.
Final management192.168.2.10. Isolated candidate only; cold PCS/external and
integrated regression pending. No SD/QSPI/bootenv writes.

Same NetworkReset bit cold PCS **1000/1000 PASS without warmup**, first frame
included; MAC/test TX/RX+1000, CRC/preamble/clock/data errors+0, raw90/82/78stages
match expected bytes/FCS. Packed decoder uses O5; checker now validates O5 orO6
using strict original port metadata and all8 truth-table rows. Eight bad INIT
variants plus invalid output metadata rejected. Initial O5 preflight failure
accessed no hardware. Evidence `network-reset-cold-pcs-20261023`. Golden restored,
three whole1GiB BIST passes PASS, lease release verified, management192.168.2.22.
Next external network regression, then consider integrated candidate.

NetworkReset isolated external regression PASS:20/20 measured ICMP,350/350
byte-exact UDP across1..1400bytes,157300bytes. MAC CRC/preamble and clock fault
increments0. Separately retained wrapper/test3-ping warmups; no external cold
qualification claim. Evidence `network-reset-external-20261023`. Golden restored,
three whole1GiB BIST passes PASS, shared lease release verified; management
192.168.2.24. Next add opt-in reset flag to integrated target and run a separate
build/ADC-DDR-dualPLL-network qualification. Existing qualified artifacts retained.

## Integrated NetworkReset candidate (2026-10-23, not yet qualified)

`IntegratedSoC` now accepts optional `network_reset=False`; the CLI exposes
`--network-reset`. `tools/build_pl.py --sfp-network-reset` accepts SFP and
integrated designs and still rejects unrelated targets. Default behavior stays
off. The same helper that passed isolated cold PMA/PCS and external regression
wraps only UDP/IP, packet test and echo FIFO. ADC capture/CDC, DDR controller,
WR phase/PLL logic and the global sys domain remain outside that reset scope.

Separate candidate build launched on Dell; elaboration completed. Routing,
setup/hold and physical qualification remain pending. Do not replace the
qualified image/bundle or program this build before checks pass.

```sh
dell-build sync kasli-linux
dell-build run kasli-linux timeout 3600 build/python/bin/python tools/build_pl.py \
  --board zc706 --design integrated --ddr-sync-reset --no-header-probes \
  --sfp-network-reset --srl-timing --seed 3 --router router2 \
  --prerouted evidence/zc706/integrated-20261013/golden-mmcm-native-prerouted.txt \
  --output-dir build/zc706-integrated-network-reset-20261023/gateware \
  --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys
```

The pinned golden preroute input must exist on Dell (source synchronization
excludes evidence; this host already has the input from qualified replay).
After a successful build fetch artifacts explicitly into a separate local work
directory. The existing ARM `pl-ddr-test`, `adc-ddr-read` and `i2c.so` from the
qualified work directory can be reused, recording their hashes. Preflight must
verify the candidate's own manifest/bitstream, timing and CSR map. Hardware runs
must use `test_integrated_hardware.py` with its shared ZC706 lease and golden
restoration. Test cold PMA/PCS first, then ADC/DDR/dual-PLL capture and external
network through switch. No hardware accessed or images overwritten at this step.

Integrated candidate offline follow-up: synthesis complete, router still active
(no final manifest/timing). Parameter-only comparison with qualified netlist
PASS for named PS7,6MMCM,1IDELAYCTRL,82IDELAYE2,107ODELAYE2,22IBUFDS,1GTX.
Changed-multiplier/missing-MMCM negative controls rejected. This is not netlist
connectivity or timing proof. Existing ARM test binaries prepared separately
with recorded hashes; no hardware access. Evidence:
`evidence/zc706/integrated-network-reset-offline-20261023`. Routing continues
under its original bounded Dell lease; next inspect result before preflight.

Integrated NetworkReset seed3 route completed but setup FAIL:SYS82.04/83.33MHz,
final hold repaired to0 violations; ADC/GTX/other clocks pass. Critical command
FIFO address->bank/control decode->distributed RAM WE path12.19ns, of which
8.48ns routing (final net4.55ns). No admission manifest/programming. Evidence
`integrated-network-reset-seed3-fail-20261023`. Separate seed4 experiment launched
with identical RTL, constraints and tools, required frequency unchanged, output
`build/zc706-integrated-network-reset-seed4-20261023/gateware`. Next inspect final
timing; if still failing, target this demonstrated DDR path for pipeline/locality
work. No hardware access or golden changes.

Seed4 routing still active. Critical-path ownership refined from generated
Verilog: storage_25 is ADC0 address/data command_buffer (538bits); storage_23
is LiteDRAMDMAWriter data FIFO (514bits), mapped to distributed RAM. Endpoint
WE is the writer data enqueue enable, not PS AXI or bank-machine FIFO. A later
pipeline candidate must preserve address/data handshake together and include
its pending valid in ADCToDDR empty/drain detection. See seed3 evidence
`path-ownership.md`. No speculative pipeline/default changes during seed4 run.

Seed4 also setup FAIL:SYS82.43/83.33MHz, final hold0. Failed route retained in
`integrated-network-reset-seed4-fail-20261023`, no hardware access. Implemented
optional full address/data elastic stage between ADC command_buffer and native
DMA writer; empty/drain includes pending stage and counters retain handshake
ownership. --adc-command-pipeline is integrated-only/default off, manifest flag
and ADC_COMMAND_PIPELINE CSR constant recorded. Seven pipeline-enabled RTL
cases PASS, including delayed data completion, backpressure/overflow, address/
data conservation, repeated capture/base changes/ADC reset, frame/config errors.
Evidence `adc-command-pipeline-20261023`. Separate seed3 build launched to
`build/zc706-integrated-network-reset-pipeline-20261023/gateware`, same83.33MHz,
NetworkReset enabled. Timing/physical tests pending; qualified defaults/artifacts
unchanged. No Vivado or hardware access in these experiments.

Pipeline candidate routing still active. Post-Yosys structural check PASS:
all24 address bits in both forward/skid register groups for each ADC have
single FDRE Q drivers with clock/non-disabled CE (96drivers retained). This
confirms the intended registered address boundary exists, not final timing.
Selected primitive parameters match qualified hardware configuration again.
Evidence `adc-command-pipeline-structure-20261023`. No hardware access or new
admission manifest; next compare routed critical path and final setup/hold.

First skid pipeline setup FAIL:SYS75.91/83.33MHz, final hold0. Critical path now
DDR arbitration->ADC1 command PipeReady payload CE,537 sink cells,13.17ns total/
11.30ns routing. Evidence `adc-skid-pipeline-fail-20261023`. Replaced optional
stage with upstream depth2/unbuffered distributed SyncFIFO: local write-occupancy
control, downstream ready affects read pointer; full beat and empty/drain checks
retained. All seven same RTL cases PASS; source hash checked before run. Separate
queue2 build launched after shared Dell became free, currently placing/routing:
`build/zc706-integrated-network-reset-queue2-20261023/gateware`. Evidence
`adc-command-queue2-20261023`. Required83.33MHz unchanged. No hardware access.

Queue2 post-Yosys write-enable isolation PASS: both2x538-bit queues map to90RAM32M
each. Tracing WE through combinational LUTs reaches exactly3 local FDREs per
card: upstream source-valid and2 occupancy bits; no DDR grant/ready terminal.
Evidence `adc-command-queue2-structure-20261023`. Router still active, no final
setup/hold/admission result; no hardware access. Next inspect final STA rather
than infer timing from this structural check.
