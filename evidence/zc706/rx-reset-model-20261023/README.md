# Interrupted RX frame model, 2026-10-23

Software RTL simulation only; no FPGA programming or network/serial hardware access.
The fake PHY models accepted byte streams, not GTX, PCS symbols, clock loss or
metastability. Actual LiteEth MAC uses 8-bit data, 2048-entry TX/RX CDC,
store-and-forward, 50 MHz sys and 125 MHz PHY clocks. Sys continues during RX reset.

`partial-matrix.log` contains the three completed cases before a 300-second
whole-matrix timeout; remaining cases were NOT_RUN to completion. A previous
longer attempt also timed out without results. The initial elaboration failure
was a Migen memory write-port `dat_r=None` simulation issue; the existing MAC
test workaround was reused. None of these incomplete runs is a full-suite PASS.

| Injected prefix | RX reset after prefix | Received after each of three TX | CRC count |
|---|---|---|---|
| 0 bytes | no | 1, 2, 3 | 0, 0, 0 |
| 0 bytes | yes | 1, 2, 3 | 0, 0, 0 |
| 12 bytes, no last | no | 0, 1, 2 | 1, 1, 1 |
| 12 bytes, no last | yes | 1, 2, 3 | 0, 0, 0 |

The last case was run separately with exit 0 (`prefix12-rx-reset.log`).
Payload-error and preamble counters stayed zero in all completed cases.
This reproduces the hardware counter pattern from an unterminated fragment,
and shows RX reset clears this particular model condition. It does not prove
that hardware has this cause or that a new reset patch is required.

Run one bounded scenario at a time on Dell (after `dell-build sync kasli-linux`):

```
dell-build run kasli-linux timeout 180 build/python/bin/python -u tools/test_sfp_rx_reset.py --prefix-bytes 12
dell-build run kasli-linux timeout 180 build/python/bin/python -u tools/test_sfp_rx_reset.py --prefix-bytes 12 --reset-rx
```

The final script asserts the observed clean and 12-byte cases. Other prefix
lengths (40, 89) remain exploratory and have no claimed qualification.

Next: trace real PHY/domain reset coverage and RX traffic after release. The
current K7 PMA code resets RX MMCM through the CDR lock timer; do not assume
that RX remained unreset. A fragment arriving after reset release is a separate
hypothesis. No production gateware change has been selected.
