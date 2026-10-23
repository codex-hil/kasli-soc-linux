# Opt-in whole-network reset candidate, 2026-10-23

Actual project NetworkReset helper model PASS: old90-byte frame committed,
40 bytes accepted at sys preamble stage, RX reset asserted, then three new
packets received1/2/3 with CRC/preamble/data errors0. Actual MAC and2048-entry
FIFOs, sys50MHz/PHY125MHz, explicit valid-byte mask. This uses the same helper
as the target, not the prior ResetInserter strategy. Functional ideal reset
lowering only; no analog, metastability or release-timing proof.

Helper creates private net_sys/net_eth_tx/net_eth_rx clock domains driven by
unchanged parent clocks. A shared reset asserts all three; upstream
AsyncResetSynchronizer releases each in its own domain. Entire UDP/IP core,
PacketTest and echo FIFO are renamed into these domains. Both ends of the
RX and TX FIFOs therefore share reset ownership. PHY/diagnostic CSR bridge,
status probes and unrelated system logic remain outside. Target reset source
is PHY software reset OR parent eth_tx/eth_rx reset. No upstream modification.

Flag --sfp-network-reset is accepted only for isolated --design sfp, defaults
off and is recorded in manifest.json/CSR constant sfp_network_reset. Qualified
integrated/golden images are untouched. Model validated MAC recovery; active
TX, full UDP/IP recovery and physical first-packet recovery remain pending.

```
dell-build sync kasli-linux
dell-build run kasli-linux timeout 180 build/python/bin/python -u tools/test_sfp_rx_reset.py --queued-frame --reset-rx --network-reset --prefix-bytes 40
dell-build run kasli-linux timeout 3600 build/python/bin/python tools/build_pl.py --board zc706 --design sfp --sfp-refclk fclk --sfp-network-reset --srl-timing --seed 3 --router router2 --output-dir build/zc706-sfp-network-reset-20261023/gateware --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys
```

Build launched on Dell under shared heavy-build lease. Elaboration completed;
synthesis/routing/timing/bitstream result pending. Do not program until timing
and manifest/artifact preflight pass. No hardware accessed in this experiment.
Next inspect build, fix any demonstrated reset/timing issue, then use existing
shared-board-lock/golden-restoring wrapper for a cold first-packet test.
