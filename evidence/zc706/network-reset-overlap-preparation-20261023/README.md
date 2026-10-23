# In-capture network reset diagnostic preparation, 2026-10-23

New opt-in --network-reset-during-capture on the existing shared-lock,
golden-restoring integration owner. Requires full external-network scope and
matching NetworkReset-enabled gateware. No new bitstream or rebuild.

For each long capture (>=1,048,576 samples), read both DMA busy flags, assert
PHY reset preserving other control bits, read reset back and require both DMA
busy flags still active. Hold2ms, always release reset in finally, and verify
release readback. These observations prove software-observed overlap, not
oscilloscope-level timing. After capture, require PHY re-lock within10s, then
verify all ADC data/counts/drops with existing ARM reader. Missed overlap FAILS;
do not count a reset between captures as a passed test.

Five offline helper tests PASS: valid overlap/control preservation, completion
before assertion (no writes), completion during assertion (FAIL but release),
unsupported bitstream (no writes), existing reset (no release of prior state).
Full artifact preflight PASS. Existing qualified package remains unchanged;
updated capture script has a new software hash and must receive new physical
validation before any repackaging against it.

Physical run launched separately, result pending. Initial captures and captures
with dual PLLs both exercise the reset hook; phase window increased to300s to
include bounded link waits, no timing/phase/error thresholds relaxed. External
network verifies final recovery after the series; it is not an active in-flight
Ethernet frame test and not continuous ADC streaming.

```
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir WORK_DIR --output UNIQUE_OUTPUT --external-network --network-reset-during-capture --program
```

All actual HW access occurs inside existing shared board lease; restoration
still runs in finally. No SD/QSPI/bootenv writes. Inspect final validation.json,
raw per-capture overlap records, phase stats and golden BIST before claiming PASS.
