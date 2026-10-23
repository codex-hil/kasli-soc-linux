# Updated reset-tested PL package PASS, 2026-10-23

Archive: /home/codex-hil/artifacts/zc706-integrated-network-reset-queue2-reset-tested-20261023/zc706-integrated-reset-tested.tar.xz
Bytes:1418748. SHA256:
b07d7b34faa91a02507dde0503d14b829cde2dc1acd12989e35cf1d6f89947ce

All33 SHA256SUMS-listed files verified. Included capture tool matches the new
physical run's hash. Verified all6 overlap records from the archive itself:
3 initial +3 with dual PLLs, both DMAs busy before/after reset readback, reset
release/relock correct, all samples/card counts/drop/data checks PASS.
Same bit7bdc77ea...83ac831 has full ADC/DDR/PLL/external Ethernet and cold PMA/
PCS qualification. Active Ethernet-frame reset is not claimed.

Previous a90b8456... package hash rechecked unchanged. No new bitstream or
hardware access in packaging. Board last restored to golden with DDR3×1GiB
PASS and released shared lease; management192.168.2.23.

```
python3 tools/package_integrated.py --work-dir WORK_DIR --evidence-dir evidence/zc706/network-reset-overlap-hardware-20261023 --validation evidence/zc706/network-reset-overlap-hardware-20261023/validation.json --loopback-validation evidence/zc706/integrated-queue2-cold-pma-20261023/validation.json --loopback-validation evidence/zc706/integrated-queue2-cold-pcs-20261023/validation.json --readme docs/zc706-integrated-network-reset.md --output NEW_ARCHIVE.tar.xz
```

Source packaging revision f593f19. Build recipe remains
`make ENV= integrated-network-reset-pl` inside prepared Dell runtime; source/
tool/preroute preparation is documented in the linked project guides.
This is a PL diagnostic bundle, NOT an SD image. It closes this ZC706 integration
qualification, not original physical Kasli-SoC milestone1. Kasli hardware
validation, continuous ADC streaming and deterministic sample alignment remain
separate pending scopes; no extra qualification is inferred.
