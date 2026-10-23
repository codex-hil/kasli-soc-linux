# Queue2 synthesized write-enable isolation, 2026-10-23

Build still routing; no final timing or admission manifest. No hardware access.
Generated Verilog identifies storage_26 and storage_31 as each card's2x538-bit
command_pipeline. Each maps to90RAM32M cells sharing a write enable.

Trace each write-enable cone through combinational LUTs to sequential inputs:
exactly3 FDRE terminals per card, named command_buffer_readable (source valid)
and the two command_pipeline_level bits. No DDR arbitration/grant terminal is
in either queue's combinational write-enable cone. Exact terminal cell names,
aliases and netlist SHA256 retained in JSON. This verifies local-occupancy
write acceptance at synthesis, not output-command timing, placement or hardware.

Previous skid implementation's critical CE drove537 registers through a DDR
grant/ready path. This structural change removes that specific dependency;
only final STA can show whether all remaining paths meet83.33MHz.
