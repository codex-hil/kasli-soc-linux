# Reset-held sys RX capture, physical ZC706, 2026-10-23

Same diagnostic bitstream ee68e220..., PMA, no warmup, strict cold test FAIL.
Opt-in --internal-capture-reset-held arms sys RX probes after PHY reset assertion
and 10ms sleep, before software releases PHY reset. This is software ordering;
there is no measured eth_rx reset waveform. Four offline sequence tests PASS.

First test packet: TX+1, MAC RX+1, test RX0, CRC+1, preamble/clock/data errors+0.
PHY TX and RX captures contain matching valid90-byte packets. Sys probes instead
captured preceding network traffic: preamble input231bytes, CRC input399bytes,
CRC output395bytes with error1. All are truncated128-byte snapshots with no
capture overflow. Independent snapshot ordinals are unknown; this does not prove
these are the same packet or the cause of the test packet loss. Arming during
asserted software PHY reset does not guarantee old sys/CDC traffic is absent.

Next simulate RX CDC with queued committed traffic and only its write domain
reset, keeping sys read state alive. The earlier incomplete-prefix model had
not exercised this queued-data reset case. No common-reset fix is proven yet.

Shared board lease held throughout JTAG/UART/network/probe/golden restoration.
Golden restored and three whole1GiB DDR BIST passes PASS. Lease reacquisition
verified. Final host in validation.json. No SD/QSPI/bootenv writes. No new bit.
