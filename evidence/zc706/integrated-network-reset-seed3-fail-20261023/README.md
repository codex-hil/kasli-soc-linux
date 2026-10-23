# Integrated NetworkReset seed3 setup failure, 2026-10-23

Routing completed but nextpnr returned1; no admission manifest/bitstream.
SYS82.04MHz fails83.33MHz. ADC1/2, GTX RX/TX and other reported clocks pass.
Final hold repair reports0 remaining violations (earlier errors in the log
include pre-repair hold reports; do not interpret the aggregate13-error count
as13 independent final failures).

Critical sys path: BRAM storage_25.DOADO8, command FIFO address bit9 through
bank/control decoding, distributed queue storage_23/DPR3_1.WE. Total12.19ns,
logic3.70ns/routing8.48ns, including final4.55ns net to distant distributed RAM.
This is a placement/routing-sensitive DDR command path, not the network-reset
signal. Same parameters as qualified reference were checked separately.

Preserve this failed run. Next experiment changes only nextpnr seed3->4 in a
separate output directory at the same required frequencies and same RTL/tool
options. No timing-ignore, frequency reduction or programming of failed result.
If that route still fails, inspect this exact command-decode/queue path before
choosing pipeline/locality changes. No hardware access; golden untouched.
