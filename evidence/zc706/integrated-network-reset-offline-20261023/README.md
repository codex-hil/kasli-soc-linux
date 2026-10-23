# Integrated NetworkReset offline checks, 2026-10-23

Candidate synthesis completed; routing is still active under the shared Dell
heavy-build lease. No final manifest/timing or programming admission yet.
Do not treat route_arc search warnings as a demonstrated failure before the
bounded router exits. Original routing job is preserved, not duplicated.

Named primitive parameter dictionaries match the qualified integrated-fixed-cdc
netlist exactly: PS7(1), MMCME2_ADV(6), IDELAYCTRL(1), IDELAYE2(82),
ODELAYE2(107), IBUFDS(22), GTXE2_CHANNEL(1). This is parameter-only comparison,
not connectivity, timing, bitstream equivalence or physical qualification.
Source netlist hashes are retained in primitive-parameters.json. Comparator
rejects a changed MMCM multiplier and a missing MMCM (negative controls).

```
python3 tools/compare_primitive_parameters.py REFERENCE_TOP_JSON CANDIDATE_TOP_JSON --output report.json
```

Qualified ARM pl-ddr-test/adc-ddr-read/i2c.so copied to the separate local
candidate work directory /tmp/zc706-integrated-network-reset-artifact, with
hashes in userspace-inputs.json. No builds/installations removed; no hardware
access. Candidate gateware will be fetched into that work directory only after
completion and verified independently before using these test programs.

Next inspect routing exit and final setup/hold, preserving logs even if failed;
then preflight and bounded cold-loopback/integration qualification through
existing shared-board-lock and golden-restoring wrapper. No HW blocker exists
at this offline stage; the current dependency is the running build result.
