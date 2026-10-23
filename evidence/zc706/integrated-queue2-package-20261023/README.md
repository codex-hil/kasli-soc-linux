# Qualified integrated PL package, 2026-10-23

Archive: /home/codex-hil/artifacts/zc706-integrated-network-reset-queue2-20261023/zc706-integrated-network-reset-queue2.tar.xz
Bytes:1416436. SHA256:
a90b84564f25115d19d51cdc64698edb92d64a6434456d9111bf56e2b2743daf

All33 SHA256SUMS-listed files verified after extraction. Artifact metadata
matches full physical integration/external Ethernet and both cold internal modes
on bit7bdc77ea...83ac831. Packaging negative controls reject wrong-bit proof,
warmup proof and a one-frame counter mismatch before creating an archive.
Qualified old packages retained. Source/recipe at repository revision0c7472e;
gateware inputs unchanged from queue2 build. This is a PL bundle, NOT SD image.

```
python3 tools/package_integrated.py --work-dir WORK_DIR --evidence-dir evidence/zc706/integrated-queue2-hardware-20261023 --validation evidence/zc706/integrated-queue2-hardware-20261023/validation.json --loopback-validation evidence/zc706/integrated-queue2-cold-pma-20261023/validation.json --loopback-validation evidence/zc706/integrated-queue2-cold-pcs-20261023/validation.json --readme docs/zc706-integrated-network-reset.md --output NEW_ARCHIVE.tar.xz
```

Build shortcut: on Dell `make ENV= integrated-network-reset-pl` after the locked
source/tool preparation and explicit sync. Hardware lease remains on Optiplex.
No hardware access in packaging. Latest board state: golden restored and DDR
BIST PASS after PCS, management192.168.2.20, shared lease released.

Remaining separate qualifications: repeated/in-flight network reset, continuous
ADC streaming and deterministic inter-card alignment. Neither this bundle nor
these tests completes the original physical Kasli-SoC Linux milestone.
