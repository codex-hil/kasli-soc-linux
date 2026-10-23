# MAC queued-frame reset characterization, 2026-10-23

Offline actual LiteEth MAC, store-and-forward and2048-entry CDC, sys50MHz,
RX/TX125MHz; no GTX/PCS or physical hardware access. A complete valid-FCS
90-byte frame is committed at PHY input. Reset is requested when12 bytes have
been accepted by the sys preamble stage (8 preamble +4 subsequent bytes).
RX domain resets while sys remains active. Only RX FIFO is changed to use
upstream with_common_rst=True by a constructor-scoped test patch; upstream
checkout and production gateware are unchanged.

Initial characterization with implicit PHY be=0: new packets RX0/1/2 for TX1/2/3,
CRC1 throughout. The final run explicitly sets injected be=1 and checks the
same counter sequence. See final-regression.log and exact command below.

This demonstrates that coherently resetting the FIFO does not, by itself,
clear a partly processed sys-domain frame. It reproduces first-packet CRC loss
under a deliberate reset condition; physical root cause remains unproven.
Combined with the independent-FIFO-reset model, a candidate recovery must
handle both FIFO pointer coherence and downstream packet-parser state.

Common reset uses the ideal functional reset lowering from test_sfp_cdc_reset;
no synchronizer-release timing or metastability proof. Sys clock aliases for
RX common FIFO are correctly125MHz write/50MHz read. Other prefix positions
and reset strategies remain NOT_RUN in this scenario.

Reproducer (final asserted command):
```
dell-build sync kasli-linux
dell-build run kasli-linux timeout 180 build/python/bin/python -u -c 'import sys,json; sys.path.insert(0,"tools"); from test_sfp_rx_reset import trial; r=trial(12,True,True,True); print(json.dumps(r,indent=2)); assert [x["rx"] for x in r["frames"]]==[0,1,2]; assert [x["crc"] for x in r["frames"]]==[1,1,1]; print("PASS: common FIFO reset leaves partial MAC state; first packet lost")'
```

Next model coherent RX FIFO plus MAC parser recovery; include deeper reset
positions before choosing a minimal implementation. No production fix claimed.
