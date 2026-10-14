# Validated ZC706 integrated core

This is a PL bring-up bundle, not an SD image. It uses the existing ZC706
Linux boot environment. It contains no SSH keys and does not write SD/QSPI/OTP.

The tested ZC706 rev1.2 has XC7Z045FFG900-2, two FMC ADC100M4cha v6.1 cards,
VADJ2.5V and independent ADC clocks. The integrated design includes PL DDR,
dual ADC DMA, two WR-derived PLL loops and internal SFP PMA/PCS/MAC loopback.

On 2026-10-14 the included bitstream passed DDR initialization/address checks,
three whole1-GiB BIST passes, dual ADC sequence/pattern capture through4194304
samples per card, concurrent acquisition with both PLLs locked and1000 SFP
loopback frames. No capture drops or data errors. Concurrent phase std was
about1.47ns per card. External SFP switch networking remains NOT_RUN.

## Rebuild

Use the pinned project environment and toolchain setup in the repository README.
No Vivado is used. From the repository root:

```sh
make integrated-qualified-pl
make integrated-qualified-software
make integrated-qualified-package
```

The PL target uses seed3, synchronized serializer reset and the exact audited
MMCM reference paths in the repository. The route file is a build constraint,
not a binary patch. The build checks setup/hold before assembly. Routing is
bounded to20 minutes with8GiB/no swap and2 CPUs; memory returns to6GiB afterward.
Build output: `build/zc706-integrated-golden-clock-clean-seed3`.

The package command requires matching physical evidence for the bitstream,
CSR map, binaries and board scripts. Source updates may change hashes; those
artifacts must be retested before publishing them as validated. It does not
silently transfer validation from an older build.

## Hardware verification

Use the current board IP in place of HOST. The wrapper acquires the shared
ZC706 lock across all programming, reset, UART, network and I2C activity,
restores the documented golden PL and qualifies restored DDR before release.
The original golden bitstream and software must remain in the workspace.

```sh
python3 tools/test_integrated_hardware.py --host HOST --program \
  --work-dir build/zc706-integrated-golden-clock-clean-seed3 \
  --output build/zc706-integrated-golden-clock-clean-seed3/integration-validation
```

External network testing is opt-in with `--external-network` and requires a
working physical module/link. Internal loopback does not prove external Ethernet.
PLL testing restores the original oscillator registers. No generator/analog
input is required: these tests use digital ADC patterns and sequence data.

## Bundle checks

```sh
tar -xf zc706-integrated-qualified.tar.xz -C DESTINATION
cd DESTINATION
sha256sum -c SHA256SUMS
```

The archive contains `integrated.bit`, `csr.json`, native board binaries/scripts,
lock files describing source/toolchain revisions, timing/build manifests and
physical test evidence. Run scripts on the board only while holding the shared
board lock via the project wrapper. See `docs/zc706-integrated.md` in the repository
for diagnostics, limitations and full history. Golden is deliberately left running
when the test ends; loading this bundle persistently is not part of the test.
