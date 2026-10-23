# Cold near-end PCS PASS, 2026-10-23

Same bit bda5b406b8b475537891e971e3b08e9efc2bc95deb3e293f62efa720c34c63a0,
NetworkReset enabled, active copper SFP, no warmup/burst. First packet and
1000/1000 frames PASS. MAC/test TX/RX+1000, CRC/preamble/clock/data errors+0.
PHY90-byte TX/RX identical with independent valid FCS, RX90/82/78 stages match.
Together with cold PMA evidence, both modes now pass without startup packet loss
in these bounded runs. Repeated/in-flight mode transitions remain pending.

Initial preflight stopped before HW because packed LUT decoder uses O5, whereas
checker only recognized O6. Added O5 support with original-output metadata
validation; all8 loopback rows match only001 asserting CDR hold. Eight INIT
bit mutations and incorrect O5 metadata rejected. Scope remains packed
connectivity/original metadata, not independent FASM proof. No bitstream change.

Shared board lease covered JTAG/UART/network/probe/golden restoration.
Golden restored, three whole1GiB DDR BIST passes PASS; lease release verified.
Final management192.168.2.22. No SD/QSPI/bootenv writes.
Next external network regression on this same candidate before integration.
