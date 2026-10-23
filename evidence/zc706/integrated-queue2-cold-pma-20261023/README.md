# Integrated cold PMA PASS, 2026-10-23

Same physically integrated-qualified bit7bdc77ea...83ac831 with NetworkReset
and queue2, no header probes. Cold near-end PMA1000/1000 packets PASS, first
packet included, no warmup/burst. MAC/test TX/RX each+1000; CRC/preamble/clock/
test-data errors each+0. No raw stage-byte capture claim on this no-probe build.

Shared ZC706 lease covered programming/JTAG/UART/network/probe/restoration.
Golden restored, three whole1GiB DDR BIST passes PASS, release verified.
Final management192.168.2.18. No SD/QSPI/bootenv writes. Next same-bit cold PCS,
then package against matching integration and internal-mode evidence.
