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

No-SRL physical control PASS:124,749 cumulative sent/received, zero errors,
gaps0/1/3, correct IP and MAC throughout. Functional Verilog is identical to
the failed SRL variant after comments are removed. Golden restored192.168.2.22
and three whole1GiB DDR BIST passes PASS; lease released/reacquirechecked.
Evidence: `evidence/zc706/arp-selftest-no-srl-20261022`. Bitstream SHA-256:
`6ba72e2cb3def2bf829c2e150e4a9485ac5498a0dc91f6f813edb05fefd7843c`.

`tools/test_arp_mapped.py` prepares standalone Yosys/ABC9-mapped versions
with and without SRL, verifies8/0 SRL cells, and runs them with the existing
OSS CAD Suite Icarus tools on Dell. Migen simulation is the RTL baseline.
A first attempt to simulate raw Migen-generated Verilog with Icarus stalled
without transcript; it is not a functional FAIL. Mapped simulation results
remain pending, and timeouts must stay distinct from field mismatches.

Confirmed mapped simulation (Dell, no nextpnr or bitstream): Migen RTL PASS;
Yosys0.52/ABC9 SRL netlist FAIL,75/75 errors and IP192.168.2.2; no-SRL
netlist PASS,151 cumulative frames across all three gap cases. This matches
the physical failure and localizes this reproducer to synthesis/technology
mapping rather than FPGA routing or FASM. Exact source/transcripts are under
`evidence/zc706/arp-mapped-20261022`; the raw-Verilog stalled attempt is not
used as RTL proof. No extra hardware tests were required.

Reproduce on Dell:

```sh
dell-build sync kasli-linux
dell-build run kasli-linux build/python/bin/python tools/test_arp_mapped.py \
  --output build/zc706-arp-mapped-confirmed
```

Next: reduce to a clock-enabled shift chain and identify where enable is
lost: the no-SRL header FFs have variable CE, while the mapped SRLs have
CE tied high. This structural difference needs pass-by-pass confirmation
before proposing an upstream fix.

Root cause confirmed with the minimal seven-FF CE reproducer:
`xilinx_srl -fixed` in the installed Yosys0.52 sets ENPOL=2 for FDRE
chains even though E is connected to CE. The mapped SRL ignores CE.
See `diagnostics/yosys-srl-ce/README.md` and upstream issue6058/PR6059.
Replacement-tool validation is pending; keep the qualified no-SRL image.
