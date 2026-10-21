# Confirmed SRL timing coverage gap

Offline audit on 2026-10-21 confirms that the exact chipdb used by the
SRL-enabled Ethernet control omits sequential timing for SRL16E data and output.
Evidence: `evidence/zc706/srl-timing-20261021`.

`tools/audit_srl_timing.py` reads schema6 binary timing tables directly. The
active chipdb SHA-256 is
`72eaa756d07ebb2a81a9a9c3189f1c3632fc7690d20252c9d70c3d54c4033d69`.
All 32 routed Ethernet SRL16E have connected DI2/O6 ports. In DEFAULT speed
grade, SLICE_LUTX has no DI2 timing entry and O6 has six combinational arcs
but no sequential arcs. The parser also verifies the expected existing DI1
and WE setup/hold entries; this is not merely a search of generator source.

Reproduce without hardware:

```sh
python3 tools/audit_srl_timing.py \
  build/zc706-sfp/chipdb-hr/chipdb-xc7z045.bin \
  --routed build/zc706-sfp-srl-control/gateware/gateware/top_routed.json \
  --output build/srl-timing-audit.json
```

The source explains how this affects analysis:

- `pack.cc:XilinxPacker::pack_srls` maps SRL16E D to DI2 and Q to O6,
  converting the primitive into SLICE_LUTX.
- `gen/xilinx_gen.py` creates only the generic SLICE_LUTX timing variant,
  with setup/hold on DI1, WE and WA pins, and combinational A-to-O arcs.
- `xilinx.cc:assign_cell_tags` identifies SRLs for placement, but does not
  choose a dedicated SRL timing variant. The active patched source agrees.
- Himbaechel `arch.cc:lookup_port_tmg_type` treats an unlisted input as
  combinational and an output without sequential arcs as combinational.
- The hold fixer consumes the timing engine's reported min-delay violations;
  it cannot repair an endpoint that was never recognized as sequential.

Consequently a clean hold report does not establish SRL16E DI2 hold coverage,
and reported setup/Fmax also excludes the corresponding registered data path.
The earlier physical primitive/CE/inference PASS results remain valid functional
measurements, but their setup/hold admission is bounded by this missing model.
This is a confirmed toolchain limitation, not yet a demonstrated cause of the
Ethernet failure. No board access or configuration changes occurred in this audit.

Project X-Ray already provides `LUT_OR_MEM6SHFREG` timing in the pinned
`zynq7/timings/slicem.sdf`: WE setup/hold, DI1/DI2 setup/hold, and clock-to-O6/
MC31 for A6/B6/C6/D6. Parsed values and source hash are retained in evidence.
Do not invent delays or add sequential O6 timing to every combinational LUT.

Next implementation: an isolated SRL-specific timing model sourced from this
SDF, selected only for SRL cells (with safe treatment of placement/clock edge).
Verify model coverage and negative controls, rebuild through the shared Dell
lease, then compare the same SRL-enabled Ethernet design under the ZC706 lease
with automatic golden restoration. Preserve the no-SRL qualified image. Dynamic
address behavior, SRLC32E and speed-grade precision need explicit scope rather
than an unqualified timing signoff.

## Isolated model implementation (2026-10-21)

`--srl-timing` selects `tools/srl_nextpnr.py` for SFP or SRL diagnostics.
It builds a separate binary under `build/zc706-srl-timing/nextpnr`, keeping
qualified binaries intact. `srl_timing_model.py` derives conservative integer-ps
bounds from the pinned SDF, rounding outward across A6/B6/C6/D6. No speed-grade
scaling is invented. Source hash and generated bounds enter the binary manifest.

`patches/nextpnr-srl-timing.inc` overrides timing only for packed SRL16E:
DI2/WE become sequential inputs and O6 a clocked output. Ordinary LUTs retain
existing timing. Inverted clocks, dynamic address inputs and non-six-LUT SRL
placement are rejected. SRLC32E is outside this experiment. Coverage and model
precision remain experimental, not a vendor timing signoff.

Offline envelope controls passed (`evidence/zc706/srl-model-20261021/model.json`).
The isolated binary compiles. First placement was rejected when a temporary
SRL candidate occupied a five-LUT position; the failure log is retained under
`evidence/zc706/srl-model-20261022`. The placement checker now rejects such
candidates, and preRoute asserts the final six-LUT positions and sequential
DI2/O6 classes. The replacement build confirms coverage for all32 SRLs and passed final
setup/hold. Physical ABI3 comparison PASS: inferred and explicit delays4/8,
zero sticky errors over about45M observed fabric cycles. Golden restoration
and three whole1GiB DDR BIST passes PASS; final management IP192.168.2.16.
Evidence: `evidence/zc706/srl-modeled-20261022`.
Bitstream SHA-256: `03f88f3aa8325564d3c5eaa0ec0ede77bca6dd291181673d45169ab79f8e65b9`.

Both build and hardware admission check runtime coverage counts against source
and routed netlists. Missing coverage, count mismatch and five-LUT placement
negative controls passed offline. A manifest timing flag alone is insufficient.

```sh
dell-build sync kasli-linux
dell-build run kasli-linux build/python/bin/python tools/build_pl.py \
  --board zc706 --design srl --srl-timing \
  --output-dir build/zc706-srl-modeled/gateware \
  --yosys /usr/bin/yosys --openxc7 build/tools/openxc7 --seed 3 --router router2
```

Next: collect compile output, resolve any model integration errors, verify
reported sequential endpoints, then qualify the diagnostic before an Ethernet
comparison. Keep existing golden restoration and shared board lease mandatory.

The next controlled SFP build is running on Dell under
`build/zc706-sfp-srl-modeled`: same functional Ethernet target, FCLK reference,
no raw header probes, SRL enabled, seed3/router2, experimental timing model.
External network hardware test FAIL: 0/20 ping, first UDP timeout.
Runtime coverage32/setup/hold allPASS, but ARP replies162, host matches0,
cache updates0, failures24. Settled CRC/preamble/clock error deltas0.
PCAP shows correct host192.168.2.107/MAC replies while PL decoded last sender
IP192.168.2.0. Functional Verilog matches the failing control after comment
removal. This timing-model intervention alone did not fix Ethernet.
Golden restored192.168.2.18; three whole1GiB DDR BIST passes PASS.
Evidence: `evidence/zc706/sfp-srl-modeled-20261022` (including PCAP).
Bitstream SHA-256: `519cecc97518c06303bdca96c850204f15aafe0f809743781502ad99c63614dd`.
Next: hardware self-test of the actual upstream ARP depacketizer driven by a
known byte stream, with no raw header taps that would inhibit SRL extraction.
Compare SRL-enabled versus no-SRL builds; keep timing coverage repair as a
separate confirmed limitation, not a proven root cause of the header failure.
