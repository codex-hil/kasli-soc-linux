# Queue2 seed3 final setup failure, 2026-10-23

SYS82.02/83.33MHz fails setup; final hold0. No admission manifest/programming.
The worst sys path moved away from ADC writer: socbushandler_count[1] through
AXI burst/control logic to AXI2AXILite ax_buffer burst bit0 synchronous reset.
Total12.19ns, logic2.48ns/routing9.71ns. Exact endpoint cell/alias identified
in the recorded source netlist; no claim of full bus protocol root cause.
The DMA structural improvement is present, but the whole design is not qualified.

Next bounded placement comparison uses identical queue2 RTL and seed4 in a
separate output directory, same83.33MHz and tools/options. This tests routing
sensitivity of the new worst path; do not program failed output or relax clock.
If still failing, investigate the demonstrated AXI burst/ready feedback path
with the existing bridge protocol tests before selecting another pipeline.
No changes to qualified golden or hardware in this step.
