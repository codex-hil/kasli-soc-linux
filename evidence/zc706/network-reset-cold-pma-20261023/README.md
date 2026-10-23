# Cold near-end PMA with whole-network reset PASS, 2026-10-23

Same active copper SFP and isolated design with opt-in NetworkReset.
Bit SHA256 bda5b406b8b475537891e971e3b08e9efc2bc95deb3e293f62efa720c34c63a0.
First packet and all1000/1000 packets PASS with NO warmup or diagnostic burst.
MAC/test TX/RX each+1000; CRC/preamble/clock/test-data errors each+0.
Raw TX/RX90-byte frames identical with independently valid FCS77b3d256;
RX-stage90/82/78 bytes exactly expected, all errors/overflows0.
Default strict test unchanged. Previous no-reset design failed packet0 under
this setup, while this candidate passed. This is hardware validation of this
build/sequence, not proof across every traffic/reset timing condition.
PCS, external network and repeated/in-flight transitions with this bit remain
pending; qualified integrated image remains unchanged.

Wrapper held shared ZC706 lease through JTAG/UART/network/probe/restoration.
Golden restored; three whole1GiB DDR BIST passes PASS; lease reacquired/released.
Final management DHCP192.168.2.10. No SD/QSPI/bootenv writes.

```
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir /tmp/zc706-network-reset-artifact --output /tmp/UNIQUE --internal-loopback-only --program
```

Next cold PCS comparison with same bit and no warmup; then external-network
regression before considering integration with ADC/DDR/PLL.
