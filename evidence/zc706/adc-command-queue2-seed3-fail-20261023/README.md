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

## Corrected counter identification

The earlier description calling socbushandler_count a burst counter was wrong.
Generated top.v declares it20bits with reset1000000. It belongs to Wishbone
Timeout/WaitTimer, whose combinational count==0 injects an ACK/timeout response.
That response reaches AXI2AXILite ax_buffer reset through bus control. Endpoint
identification remains correct; the startpoint is the timeout, not AXIBurst2Beat.

If seed4 still fails this path, a candidate is a registered terminal flag with
exact same timeout cycle: for wait=1, done_next=(count<=1), alongside saturating
countdown; for wait=0, done_next=(reload==0), alongside count reload. This equals
(count_next==0), so a register need not add a timeout cycle. Mathematical identity
checked exhaustively for reload0..64/all reachable count values/wait0/1. This
is arithmetic analysis only, not HDL/reset/bridge qualification. Production
reload1000000 and default behavior have NOT been changed. A real candidate
would require RTL comparison including reset/cancel/restart and bridge tests.
