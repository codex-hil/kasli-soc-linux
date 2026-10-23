# Queued RX CDC reset characterization, 2026-10-23

Offline actual upstream LiteX ClockDomainCrossing/AsyncFIFO simulation. No HW.
Depth32, unbuffered, clocks RX125MHz/sys50MHz; ten old bytes queued, four read,
consumer paused, optionally RX/write domain reset while sys continues, three
new bytes160/161/162 queued, then consumer resumed for90 sys clocks.

- No reset: exactly old bytes4..9 followed by160..162; both last markers intact.
- RX/write-only reset, independent FIFO resets: incorrect stream, repeated zeros
  and repeated new bytes (two160..162 groups in the observation window).
- RX reset with upstream with_common_rst=True: exactly160..162, one final last.

Final script clean-control/common-flush assertions PASS. Independent-reset
output is retained as characterization, not an exact uninitialized-data oracle.
This demonstrates reset pointer incoherence for this controlled scenario. It
is not a proof that the physical first-packet loss has the same cause.

Migen reset synchronizer special is lowered to an ideal combinational reset
for simulation. This verifies logical pointer reset behavior only, not real
asynchronous assertion, synchronized deassertion timing, metastability or GTX.
Internal common-reset clock aliases are simulated at their parent rates.
Initial elaboration hit the existing Migen write-only memory dat_r=None issue;
the same workaround as the other MAC simulations was applied before final run.

Reproducer:
```
dell-build sync kasli-linux
dell-build run kasli-linux timeout 90 build/python/bin/python -u tools/test_sfp_cdc_reset.py
```

Next: exercise queued traffic and partial sys-domain CRC/preamble state in the
full MAC with coherent FIFO reset. Flushing the FIFO alone might leave a partial
frame downstream, so do not yet apply or claim a production reset fix. No new
FPGA build or hardware access in this experiment.
