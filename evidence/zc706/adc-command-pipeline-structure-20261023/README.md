# Pipeline synthesis structure, 2026-10-23

Pipeline candidate synthesis completed, router still running; no final timing,
admission manifest or hardware access. Previous qualified images retained.

All24 address bits for each of the two cards, in both PipeValid output and
PipeReady skid-storage groups, have exactly one FDRE Q driver, a clock input
and non-disabled CE. 96 address-register drivers recorded with netlist SHA256.
Thus the address register boundary exists after Yosys, not optimized to a direct
BRAM-to-decoder wire. This does not prove final ready/control paths meet timing.
The seven RTL cases separately checked complete address/data handshake behavior.

Selected hardware primitive parameters still match qualified integrated netlist:
PS7,6MMCM,1IDELAYCTRL,82IDELAYE2,107ODELAYE2,22IBUFDS,1GTX. This parameter-only
check is not full connectivity or physical equivalence. See JSON scopes.

Next inspect final routing setup/hold and compare critical path with the failed
seed3/4 routes. Only timing-clean matching artifacts may reach shared-lock
hardware wrapper; no frequency relaxation or timing-ignore permitted.
