# ZC706 live SD-runtime soak

Physical result2026-10-27: **PASS**,600.30 seconds with the installed standalone
SD image and existing continuous dual WR PLL service. No reset, clock
reinitialization, firmware reload, SD Wire switch, boot-image write or analog
frontend setting change. The same PLL process (PID120) remained active.

## Results

Element | Observation
---|---
PLL status |195 sampled observations; both locked, status3, no new rejected phase events
Status freshness |194 consecutive intervals independently checked for advancing elapsed time and both hardware event counters; no stall/reset
FMC1 sampled phase |peak4.127ns, mean0.099ns, stddev1.452ns
FMC2 sampled phase |peak3.968ns, mean0.050ns, stddev1.435ns
ADC→DDR |4 batches,20 dual-card acquisitions /40 card buffers
Verified data |102,825,984 samples /822,607,872 bytes (784.5MiB), zero verification errors/drops
Largest buffer |4,194,304 samples /32MiB per card; independent clocks and capture epochs
SFP through switch |28,000/28,000 exact UDP replies (1..1400-byte payloads),80/80 qualification ICMP; warmup separate
MAC/PHY |CRC/preamble/clock error deltas0; PL UDP RX/FIFO/TX counters each advanced exactly28,000
Host connection |enp2s0,1Gb/s full duplex observed; management connectivity unchanged
Linux kernel log |Unchanged over the run; no new messages
Restoration |ADC pattern registers and DMA/control configuration restored with readback; same PLL service retained, both locked

The phase statistics describe **sampled status**, not continuous jitter
measurement or proof that no sub-sampling-interval excursion occurred. Samples
were approximately3s apart. Hardware rejection counters were checked too.
An independent replay of all195 retained snapshots checked freshness, process
identity and counter progress. Six offline controls cover stale status, stalled
or reset counters, PID replacement and valid32-bit wrap.

ADC data uses real receiver digital patterns plus synthetic sequence tests.
This is repeated finite acquisition into reused buffers, not ten minutes of
continuous eight-channel streaming and not784.5MiB of unique DDR addresses.
The tests preserve the cards' independent clocks and do not prove deterministic
sample alignment. No generator, gain, offset or analog50-ohm termination test
was performed. Analog wiring confirmation and physical cold power-cycle remain
pending; the existing SD-boot proof used PS reset.

## Reproduce

The board must already run the qualified SD runtime with both PLLs locked,
the matching CSR map, installed ARM reader and capture tools. Confirm the
actual management DHCP address and existing SSH identity first.

```
python3 tools/test_sd_runtime_soak.py --host ACTUAL_IP --seconds 600 --output UNIQUE_OUTPUT
python3 tests/test_soak_progress.py
```

The wrapper owns the shared ZC706 and SDWire leases for the entire run,
validation and restoration. Four batches start near0/150/300/450s. Each uses
the existing preinitialized capture script and1000 repetitions of the seven
UDP sizes, concurrently. It snapshots ADC pattern/control/DMA configuration,
does not restart the PLL service, checks every stored sample through the
installed ARM reader, then restores the saved fields with readback. An active
DMA prevents restoration rather than resetting only its receiver. Child
captures have a separate bounded process-group owner and interruption cleanup.

Initial PHY/DDR training, bus timing/hold and bitstream qualification remain
the existing integrated evidence; this soak does not rebuild gateware.
The installed capture script matches the checkout, and post-run collection
also verified the reader hash against the SD image manifest. Future wrapper
preflight includes reader hashing and host-link inventory; the physical run's
host-link observation was collected during the test and retained as such.

Evidence: `evidence/zc706/sd-runtime-soak-20261027`. Full195 status snapshots,
raw host logs and the first sequence buffers from both cards in each batch
are retained in the checksummed archive referenced by `raw-archive.json`.
The independent audit validates the full capture/packet totals and compares
kernel logs. Service/ADC state restoration and shared-lease reacquisition PASS.

## Live analog follow-up — 2026-10-28

Physical CH1 analog acquisition PASS with the installed SD runtime and continuous
PLL service. User confirmed AFG CH1 split in parallel to CH1 of both FMCs.
Serial-selected AFG1062 1544477 readback: SIN, output ON, 1 MHz, 1.001 Vpp,
zero offset. Generator settings were already correct and were not changed.
Both analog inputs used ±5 V range with analog 50 Ω OFF.

Under the sorted board, SD Wire and generator leases, snapshot receiver control,
SSR, ADC registers 3/4 and DMA base/length/synthetic before running on the board:

```sh
cd /opt/zc706-integrated
python3 capture_adc_ddr.py --csr-json /etc/litex/csr.json \
  --reader ./adc-ddr-read --max-samples 262144 --preinitialized \
  --realtime-start --analog --output /tmp/analog-capture
```

Restore and verify the saved fields afterwards, even on failure; never reset
an active DMA. This command leaves frontend settings changed by itself.
The bounded orchestration used the soak STATE_HELPER extended with adc_ssr;
all saved values were restored and verified. No service stop, receiver clock
initialization, PL programming, reset or boot-media write occurred.

Each card stored 262144 analog four-channel ticks (2 MiB/card). Beginning,
middle and end 1024-sample windows passed sine fitting, R² > 0.99993 and
no clipping. Nominal uncalibrated amplitudes: LPC 0.929 Vpp, HPC 1.021 Vpp.
This amplitude difference remains open for calibration; it was not corrected
in the data. Frequency fits assume nominal 100 MS/s and are not a ppm/jitter
measurement. Separate acquisition epochs do not prove phase alignment.
The accompanying sequence and real ADC digital-pattern runs also passed;
all five dual captures reported zero drops and successful GP1 readback.

PLL service PID120 unchanged, both locked before/after, event counters
advanced. This is sampled evidence, not continuous lock monitoring.
See [evidence](../evidence/zc706/sd-analog-live-20261028/validation.json) and
[waveforms](../evidence/zc706/sd-analog-live-20261028/ddr-waveforms.png).
Raw 2 MiB/card buffers are retained locally in
`build/analog-live-20261028T102134Z`; hashes are in validation.json.
