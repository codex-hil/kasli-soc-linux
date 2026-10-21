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
