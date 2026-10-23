# PHY reset during dual ADC acquisition PASS, 2026-10-23

Same integrated bit7bdc77ea...83ac831, no FPGA rebuild. Full owner with
--external-network --network-reset-during-capture completed PASS.
Six resets:3 during initial long captures and3 during long captures with both
WR PLLs running. For each, both DMA busy flags were1 before PHY reset and
immediately after reset readback24; reset released back to8 and link status
returned127. All4,194,304 samples/card verified after each long capture,
zero drops/data errors, including ADC patterns and repeated synthetic runs.

This is software-observed reset/capture overlap, not oscilloscope timing proof.
External link recovery checked after each capture, then20/20 measured ICMP and
350/350 byte-exact UDP PASS after the series. No new MAC CRC/preamble/clock
errors during measured traffic. No claim that an Ethernet packet was in flight
at reset; continuous ADC streaming/deterministic inter-card alignment unqualified.

Both PLLs stayed within existing capture-window limits over24,967/24,968 records:
stddev1.897/1.887ns, mean0.00556/0.00524ns, peak9.524/9.206ns. Same thresholds
as before;300s run window accommodates bounded relock waits. Full raw records
archive retained locally with SHA, curated summary/counts included.

Shared lease held across JTAG/UART/network/ADC/PLL and restoration. Golden
restored and three whole1GiB DDR BIST passes PASS; lease reacquisition verified.
Final management192.168.2.23. No SD/QSPI/bootenv writes. Existing qualified
bundle unchanged; updated capture script has now received matching physical
qualification and can be packaged against this validation.

```
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir WORK_DIR --output UNIQUE_OUTPUT --external-network --network-reset-during-capture --program
```
