# Integrated ADC/DDR/dual PLL/external SFP PASS, 2026-10-23

Physical ZC706 rev1.2, both FMC ADC100M4cha cards, independent ADC clocks.
Bit SHA256 7bdc77eaf6176facf147f43d2c0ee2ed2833e5ea1057a644d2431be3e83ac831:
NetworkReset + local-occupancy command queue2, router2/seed4, Yosys/openXC7,
SRL enabled, experimental SRL timing. SYS91.70/83.33MHz setup and hold PASS.

- Linux boot, DDR init/leveling and three whole-1-GiB BIST passes PASS.
- Both ADC streams: finite captures up to 4,194,304 samples/card, sequence and
  ADC test patterns, exact data verified, written counts correct and drops0.
  About800MB/s/card (1.6GB/s aggregate finite capture); not continuous streaming.
- Concurrent captures with both WR PLLs running PASS. Phase over capture window:
  23,533 records/card, stddev1.5763/1.5692ns, mean0.0195/0.0182ns, peak7.4603ns.
- External SFP through switch:20/20 qualification ICMP,350/350 byte-exact UDP
  echoes sizes1..1400, no new CRC/preamble/clock errors. Test warmup retained.
- Internal PMA/PCS explicitly NOT_RUN on this integrated bit. Isolated reset
  candidate passed both without warmup; integrated cold-loopback remains next.

The bounded owner held the shared ZC706 lease throughout JTAG/UART/network,
calibration, captures, PLL control and golden restoration. Golden restored,
three more whole-1-GiB BIST passes PASS, lock reacquisition verified. Final
management DHCP192.168.2.8. No SD/QSPI/bootenv writes. Existing golden retained.

Live commentary prematurely suspected the180s PLL window had expired before
network completed. Final wrapper result is PASS: the PLL process was still
active when concurrent tests finished, and all phase-window checks passed.
No harness duration/policy change was made. Final validation.json is authoritative.

Full board archive with raw PLL records saved as local artifact with hash in
raw-archive.json; curated JSON here includes exact phase statistics and count/
SHA summary. This is qualification evidence, not an SD image.

```
.venv/bin/python tools/test_integrated_hardware.py --host ACTUAL_IP --work-dir /tmp/zc706-integrated-queue2-seed4-artifact --output /tmp/UNIQUE --external-network --program
```

Build recipe: integrated NetworkReset recipe plus --adc-command-pipeline and
--seed4, output build/zc706-integrated-network-reset-queue2-seed4-20261023/gateware.
Next qualify cold internal PMA/PCS on the integrated bit before packaging it.
Active-transfer reset recovery and continuous ADC streaming remain pending.
