# Integrated cold PCS PASS, 2026-10-23

Same bit7bdc77ea...83ac831 as integrated external/ADC/DDR/dual-PLL qualification
and cold PMA. PCS1000/1000 PASS, first packet included, no warmup/burst. MAC/test
TX/RX+1000; CRC/preamble/clock/test-data errors+0. No raw probes in this build.
Shared board lease held through programming/JTAG/UART/network/restoration.
Golden restored, three whole1GiB BIST passes PASS, release verified; management
192.168.2.20. No SD/QSPI/bootenv writes. Next verified PL bundle packaging.
