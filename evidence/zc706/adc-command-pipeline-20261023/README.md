# Opt-in ADC native-command beat pipeline, 2026-10-23

After both seeds3/4 failed83.33MHz setup, add upstream stream.Buffer with
pipe_valid/pipe_ready between each ADC command_buffer and LiteDRAMDMAWriter.
Full address/data beat is pipelined together. Pending stage valid participates
in empty/drain detection; address advances at enqueue and accepted-word counter
stays at writer.sink handshake. No upstream edits or default enable changes.

CLI --adc-command-pipeline is integrated-only and recorded in manifest; CSR
constant ADC_COMMAND_PIPELINE=1 marks enabled designs. NetworkReset remains
independent and opt-in. Qualified artifacts are retained unchanged.

Seven bounded RTL cases PASS with pipeline enabled, each exercising two
independent ADC clocks and existing native command/data handshake checks:
length8, length16 with delayed data acceptance, length256, overflow under
length1024/full stall, real input, bad frame, invalid length7. Non-stall runs
include three captures, changed base and ADC reset/rearm. Exact data/address
and written/dropped conservation checks retained; new completion assertion
rejects done while accepted commands still await data. Functional simulation
only, not PHY/DDR physical or setup/hold qualification.

```
dell-build sync kasli-linux
dell-build run kasli-linux timeout 300 build/python/bin/python -u -c 'import sys; sys.path.insert(0,"tools"); from test_adc_ddr import exercise; cases=[dict(length=8),dict(length=16,delayed_data=True),dict(length=256),dict(stall=True,length=1024),dict(real=True),dict(frame_bad=True),dict(invalid=True,length=7)]; [(exercise(command_pipeline=True,**case),print("PASS:",case,flush=True)) for case in cases]'
```

New separate build launched on Dell, seed3, same83.33MHz, DDR sync reset,
NetworkReset enabled and no header probes. Output:
build/zc706-integrated-network-reset-pipeline-20261023/gateware.
Build/timing/physical result pending. No hardware accessed. Next inspect final
setup/hold and admission metadata before any programming via shared board lease.
