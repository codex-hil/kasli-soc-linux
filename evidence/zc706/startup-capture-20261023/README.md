# Early sys-domain capture, physical ZC706, 2026-10-23

Same timing-clean diagnostic bitstream ee68e220..., near-end PMA, no warmup.
New opt-in `--internal-capture-startup` arms three sys-domain RX probes before
mode/reset and does not rearm them afterward. TX/RX-domain probes still arm
after lock because RX-domain reset would destroy early arming. Each probe
captures its first complete frame independently, not a continuous trace.
Three offline tests verify ordering, default behavior and invalid scope rejection.

Physical strict packet test FAIL: first TX+1, MAC RX+1, test RX+0, CRC+1,
preamble+0 and clock faults+0 during the test packet. Before mode/reset MAC
had RX159/CRC0/preamble0; after lock RX168/CRC0/preamble2. Thus CRC increments
with the first test packet, not during the preceding startup traffic.
TX/RX PHY captures are identical 90-byte test frames with expected FCS.

Early sys probes captured preceding external network traffic: rx_cdc length314,
CRC input456/output452, each truncated to128 bytes. These are independent
first-complete snapshots, not matching frame ordinals. They cannot prove
cross-stage corruption, CRC validity of the truncated frames, or absence of
an interrupted frame during reset. The observation does not fix or fully
explain the first-packet loss. Next isolate captures to a post-reset trigger
or add a bounded trace of valid/last/reset and frame ordinal at the RX boundary.

Wrapper held shared ZC706 lease through JTAG/UART/network/probe/restoration.
Golden restored, three whole1GiB BIST passes PASS; lease reacquisition verified.
Final management DHCP192.168.2.18. No SD/QSPI/bootenv writes. No new bitstream.
