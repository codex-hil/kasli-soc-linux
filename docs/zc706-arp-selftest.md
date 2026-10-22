# ARP depacketizer hardware self-test

Status (2026-10-22): Dell simulation PASS and synthesis inventory PASS;
route/setup/hold/runtime coverage PASS; hardware reproduces the failure. Evidence:
`evidence/zc706/arp-selftest-20261022`.

`gateware/zc706_arp.py` instantiates the unchanged upstream LiteEthARPRX.
A byte-stream injector repeatedly sends a known28-byte ARP reply plus18
padding bytes. Three configurations insert0/1/3 idle cycles between bytes.
A31-cycle inter-frame wait drains the receiver. Stopping the injector
finishes the current frame before accounting is checked.

The receiver must report sender IP192.168.2.107 and MAC6c:2b:59:f4:76:e8,
opcode reply, and exactly one event per injected frame. Counters, sticky
error count and last decoded sender are available through GP0 CSR. No full
raw-header snapshot is present. There is no GTX, SFP clock initialization,
MAC RX or PL DDR in this image. The existing LED probe remains available.

Synthesis confirms exactly8 SRL16E, each tap6 and CE=1, matching the ARP
header storage in the failing Ethernet target. The checker rejects missing
SRLs, different tap depth or CE. `--no-srl` supports a separate control image;
it is not a replacement for preserving the failing SRL result.

Build (shared Dell lease; never invoke a new heavy build locally):

```sh
dell-build sync kasli-linux
dell-build run kasli-linux build/python/bin/python tools/test_arp_selftest.py
dell-build run kasli-linux build/python/bin/python tools/build_pl.py \
  --board zc706 --design arp --srl-timing \
  --output-dir build/zc706-arp-selftest/gateware \
  --yosys /usr/bin/yosys --openxc7 build/tools/openxc7 --seed 3 --router router2
```

Fetch the completed
`build/zc706-arp-selftest` directory before qualification.

```sh
python3 tools/test_integrated_hardware.py --host CURRENT_IP \
  --work-dir build/zc706-arp-selftest --srl-diagnostic-only --program \
  --output build/zc706-arp-selftest/hardware
```

The existing bounded wrapper holds the shared ZC706 lease across boot,
CSR testing and golden restoration plus three whole1GiB DDR BIST passes.
Its historical `--srl-diagnostic-only` flag now selects either SRL or ARP
self-tests from the verified build manifest. `tools/test_arp_csr.py` is a
board-side helper, not an independent lease owner.

Before hardware it requires matching bitstream hash, setup/hold, explicit
runtime timing coverage for all SRLs, final six-LUT placement and the exact
ARP synthesis inventory. Do not waive any failed admission.

A PASS isolates a functioning ARP RX for these injected streams; it does
not qualify the MAC/CRC/CDC/network path. A FAIL should be compared with
the no-SRL control and the retained simulation before attributing a tool stage.

Physical SRL-enabled result: FAIL, gap0;61,830 sent and61,830 received,
61,830 errors. Last IP192.168.2.2 instead of192.168.2.107; last MAC
6c:2b:59:f4:76:e8 correct. Simulation of this test passed. This isolates a
failure without GTX/MAC, but does not yet distinguish synthesis from routed
implementation. Gaps1/3 were NOT_RUN after the first failed case.

Golden restoration PASS at192.168.2.20, three whole1GiB DDR BIST passes PASS;
shared lease released and nonblocking reacquisition checked. NoSD/QSPI/OTP/Si
writes. Bitstream SHA-256:
`1e3c2cf8a066fdda771b7d90aa3b01f9d43bbb66025fdcf88906a92727ae3f4e`.
Next: no-SRL hardware control and mapped-netlist simulation, preserving this
failed result. Do not claim which tool is responsible before that comparison.
