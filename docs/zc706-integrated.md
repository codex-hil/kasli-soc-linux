# ZC706 integrated acquisition and clock discipline

Development target: `make integrated-pl`. This reuses the qualified dual-card
ADC/DDR target and the SFP subsystem, adding two original WR DDMTD detectors.
Physical integration validation is pending; standalone subsystem results do not
qualify this target.

The DDR controller remains at 83 1/3 MHz, with its qualified MMCM and BUFG
placements. The WR helper is derived directly from PS FCLK0 (100 MHz), at
98.4375 MHz; both ADC sample clocks are compared to FCLK0. ADC receivers and
DMA retain independent domains and asynchronous FIFOs. PLL locking does not
establish a shared acquisition epoch.

CSR banks 1–15 retain the ADC/DDR ABI. Reciprocal counters occupy 16–18,
WR phase detectors 19–20, and SFP diagnostics/MAC/packet test 21–23.
Reciprocal timestamps use the DDR system clock; software uses the exported
reference frequency rather than assuming 100 MHz. Phase units remain 10/63 ns.
SFP uses the Si5324 125 MHz reference, the existing MAC/IP and UDP echo port.
Board I2C is shared by control software; it must have one owner per transaction.

Initialize DDR and train both receivers before starting the dual PLL runner
with `--preinitialized`. Do not initialize/reset receivers while acquisition
or the PLL control loop is running. No flash, OTP or default SD boot changes.

Build and verification commands:

```sh
make integrated-pl integrated-software
python3 tools/test_integrated_hardware.py --host BOARD_IP --program --output build/zc706-integrated/hardware
```

The host wrapper owns the ZC706 lock throughout JTAG boot, training and tests.
It uses volatile JTAG programming, verifies uploaded file hashes and retains
logs, phase records and board-side capture results. The initial test includes
1,000 complete SFP MAC/PCS/GTX loopback packets. External tests use ICMP and
byte-exact UDP echo through the switch while acquisition and PLL control run.

Regression checks passed: independent-clock ADC DMA simulation (stalls,
overflow, reset, frame failure, invalid configuration), original WR dual
DDMTD simulation, PI model, I2C fault handling and parallel control ownership.
Standalone SFP CSR export remains byte-for-byte equivalent as a parsed map.
