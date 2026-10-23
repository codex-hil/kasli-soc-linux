# ADC command queue2 candidate, 2026-10-23

Replaces first command-pipeline stream.Buffer with upstream unbuffered SyncFIFO,
depth2, distributed memory. Local occupancy controls input ready/write enable;
distant native command-ready advances a read pointer instead of driving537
wide skid capture enables. Full address/data beat retained, pending source.valid
remains in empty/drain check; accepted-word and address-advance ownership unchanged.
Option --adc-command-pipeline still defaults off; no upstream edits.

Seven same RTL cases PASS: lengths8/16/256, delayed data, length1024/full-stall
overflow, real input, bad frame and invalid length7. Non-stall tests include
three captures/base changes/ADC reset. Assertions retain exact addresses/data,
write/drop conservation and no done while accepted writes await data. sys/ADC
clock periods12/10/14ns are independent. This is functional model qualification,
not timing or physical DDR qualification.

Shared Dell was busy, so sync/test/build waited. SHA256 check in launch job
verified adc_ddr_writer.py before tests; only successful tests launched the new
build. Source hash retained. Build output is separate:
build/zc706-integrated-network-reset-queue2-20261023/gateware; seed3, router2,
83.33MHz required, DDR sync/network reset/SRL timing enabled, no header probes.
Placement/routing still running; setup/hold and physical results pending.

Reproducer: same seven-case command in ../adc-command-pipeline-20261023/README.md
with this source revision; same integrated build recipe with output directory
above and --adc-command-pipeline. No hardware access, no image/flash writes.
Next inspect final timing before existing board-lock/golden-restoring wrapper.
