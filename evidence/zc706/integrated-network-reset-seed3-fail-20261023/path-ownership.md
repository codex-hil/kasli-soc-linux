# Critical path ownership follow-up

The synthesized Verilog identifies the endpoint more precisely:

- storage_25:16 words x538 bits, ADC0 command_buffer (address+data+stream markers),
  mapped to RAMB18E1; source DOADO8 carries command address bit9.
- storage_23:16 words x514 bits, ADC0 writer.fifo (data+markers),
  mapped to RAM32M; endpoint DPR3_1.WE is data FIFO write enable.

Thus this is the native LiteDRAM DMA command-acceptance/data-enqueue path,
not PS AXI bridge timing and not a bank-machine command FIFO itself. Bank/
crossbar ready decoding is upstream of writer FIFO write acceptance.

If the same RTL seed4 experiment also fails, a focused candidate is a full
address/data stream buffer between command_buffer.source and writer.sink,
using upstream stream.Buffer with both valid and ready pipelining. Do not
register ready alone or delay only address: handshake/data alignment must be
preserved. The ADCToDDR empty/drain expression must include the new stage's
source.valid; otherwise done/restart may discard a pending beat. Keep the
accepted-word counter at writer.sink handshake, and address advancement at
command_buffer.sink handshake.

Existing tools/test_adc_ddr.py exercises two independent ADC clocks, downstream
stalls and command/data conservation; use Dell for a candidate simulation and
add a focused delayed-final-beat/drain/restart case if implementing this stage.
No pipeline change has been made while the unchanged-RTL seed4 build runs.
A BRAM mapping/locality experiment on writer.fifo is another possible targeted
change, but do not combine untested strategies or modify qualified defaults.
