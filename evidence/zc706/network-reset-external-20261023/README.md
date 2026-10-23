# External SFP regression with NetworkReset PASS, 2026-10-23

Same isolated timing-clean bit bda5b406...c63a0, opt-in network reset, active
copper SFP through laboratory switch. 20/20 qualification ICMP and350/350
byte-exact UDP echoes, sizes1/17/64/128/512/1024/1400,157300 bytes total.
MAC CRC/preamble and clock fault counter increments0 during measured traffic.
Wrapper link warmup and network-test warmup each3 pings are separately recorded;
this is external regression, not an external cold-first-packet qualification.
Cold PMA/PCS tests independently passed1000/1000 each without warmup.

Shared ZC706 lease held across JTAG/UART/network/tests/restoration. Golden
restored, three whole1GiB DDR BIST passes PASS; lease reacquisition verified.
Final management DHCP192.168.2.24. No SD/QSPI/bootenv writes.

```
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir /tmp/zc706-network-reset-artifact --output /tmp/UNIQUE --sfp-diagnostic-only --program
```

Next expose this optional recovery in integrated ADC/DDR/dual-PLL target,
build separately and qualify integration. Existing integrated/golden artifacts
remain unchanged. Active-transfer reset recovery is still a separate pending test.
