# MAC sys-state recovery model, 2026-10-23

Offline actual MAC, store-and-forward/2048-entry RX/TX CDC, 125MHz PHY and50MHz
sys. Test-only constructor patch enables upstream common reset for RX FIFO;
whole MAC sys state and PacketTest diagnostic consumer are reset while RX
reset is asserted. The sys clock/other sys logic continue. Production/upstream
checkouts are unchanged. This is not a minimal production patch.

Reset occurs after a committed90-byte old frame has reached the sys preamble
input:12 bytes (early header) or40 bytes (payload). Initial interrupted frame
is intentionally discarded. Assertions require all three subsequent packets
received from the first attempt, no CRC/preamble/data errors. Completed runs
and exit status are recorded in the accompanying logs. Both12-byte and40-byte
runs exited0: RX1/2/3 for TX1/2/3, CRC/preamble/data errors0 throughout.

The model enables common reset on TX FIFO too, but there is no TX in flight
at reset. ResetInserter resets sys statements without asserting global sys
ResetSignal; it does not automatically propagate to TX FIFO local reset aliases.
Thus active-TX reset/flush is explicitly NOT qualified. RX FIFO common reset
is driven by the actual RX domain reset. A production candidate must address
both FIFO reset domains explicitly and all protocol consumers that retain a
partial packet. The test consumer reset must not be mistaken for automatically
recovering every production UDP/IP consumer.

Ideal reset synchronizer lowering verifies functional state only; no CDC
metastability, synchronized-release timing, GTX or physical root-cause proof.
Earlier common-FIFO-only model lost the first new packet with CRC+1. This
experiment checks whether clearing downstream state removes that controlled
failure. Deeper FCS-boundary reset and repeated/active-TX resets remain pending.

Reproducer, one bounded run per position:
```
dell-build sync kasli-linux
dell-build run kasli-linux timeout 180 build/python/bin/python -u tools/test_sfp_rx_reset.py --queued-frame --common-cdc --reset-rx --reset-mac --prefix-bytes 12
dell-build run kasli-linux timeout 180 build/python/bin/python -u tools/test_sfp_rx_reset.py --queued-frame --common-cdc --reset-rx --reset-mac --prefix-bytes 40
```

No hardware access or new bitstream. Next translate the verified recovery
requirements into an opt-in isolated SFP diagnostic, with explicit FIFO reset
ownership and protocol-state scope, then check timing before physical testing.
