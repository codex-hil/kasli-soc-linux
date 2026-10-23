# PCS CE-gap boundary regression, 2026-10-23

Digital simulation of actual LiteEth PCSTX encoder -> PCSRX decoder/FSM/buffer,
8-bit stream, always-ready consumer, 1000-Mbit speed setting. No GTX, MMCM,
MAC/CDC, analog clock recovery, symbol corruption or physical hardware model.

Control: three 90-byte streams each terminate normally, no errors.
After twelve accepted RX bytes, suppress decoder CE for 200 cycles while TX
continues: PCSRX eventually emits a 14-byte packet with last=1 and error=1,
then both following 90-byte packets terminate normally without errors.
The exact byte count is specific to this synchronous model and pipeline timing.
`summary.json` records boundaries; `regression.log` retains every accepted byte.

Both cases assert their observed boundaries and pass in the final script:

```
dell-build sync kasli-linux
dell-build run kasli-linux timeout 90 build/python/bin/python -u tools/test_sfp_pcs_boundary.py
```

This narrows the interrupted-frame hypothesis: a CE gap alone does not leave
an unterminated packet here. The earlier artificial no-last fragment model
reproduces CRC+1/first-packet loss, but does not yet demonstrate that real PCS
creates that fragment. Do not infer hardware damage, a toolchain defect or a
proven reset fix from either simulation.

Next diagnostic: arm startup RX observation before the mode/reset sequence,
rather than after lock/warmup; retain startup traffic separately from strict
packet qualification. Existing golden-restoring wrapper and shared ZC706 lease
must cover any physical run. No hardware was accessed for this regression.
