# SPDX-License-Identifier: BSD-2-Clause
"""Same-cycle per-bank address registers for a registered LiteX CSR bridge."""
from migen import Module, Signal, Instance, ClockSignal, ResetSignal
from migen.genlib.fsm import NextValue
from migen.fhdl.visit import NodeTransformer
from migen.fhdl.structure import _Assign


class _CaptureAddressUpdate(NodeTransformer):
    def __init__(self, address, data, enable):
        self.address, self.data, self.enable = address, data, enable
        self.updates = 0

    def visit_statements(self, statements):
        result = []
        for statement in statements:
            if isinstance(statement, NextValue) and statement.target is self.address:
                result.extend([statement, self.data.eq(statement.value), self.enable.eq(1)])
                self.updates += 1
            else:
                result.append(self.visit(statement))
        return result


class CSRAddressReplication(Module):
    def __init__(self, bridge, interconnect, slaves):
        if bridge.fsm.finalized:
            raise RuntimeError('Replicate CSR address before FSM finalization')
        address = bridge.csr.adr
        data = Signal.like(address, name='csr_address_next')
        enable = Signal(name='csr_address_update')
        # Preserve the shared decode boundary before the distributed bank FFs.
        # Keep transaction latency and address/strobe alignment unchanged.
        data.attr.add('keep')
        enable.attr.add('keep')
        bridge.comb += [data.eq(0), enable.eq(0)]
        capture = _CaptureAddressUpdate(address, data, enable)
        for state, statements in bridge.fsm.actions.items():
            bridge.fsm.actions[state] = capture.visit(statements)
        if capture.updates != 2:
            raise RuntimeError('Expected registered Wishbone2CSR capture and clear')
        # Remove only the shared address assignments. Data/strobes/read mux
        # retain the original LiteX implementation and transaction latency.
        targets = {id(slave.adr) for slave in slaves}
        assignments = interconnect._fragment.comb
        removed = [s for s in assignments if isinstance(s, _Assign) and id(s.l) in targets]
        if len(removed) != len(slaves):
            raise RuntimeError('Unexpected CSR interconnect address wiring')
        interconnect._fragment.comb = [s for s in assignments if not (isinstance(s, _Assign) and id(s.l) in targets)]
        self.addresses = []
        for bank, slave in enumerate(slaves):
            local = Signal.like(address, name=f'csr_local_address_{bank}')
            self.addresses.append(local)
            for bit in range(len(address)):
                register = Instance('FDRE', name=f'csr_address_{bank}_{bit}',
                    p_INIT=0, i_C=ClockSignal(), i_CE=enable,
                    i_R=ResetSignal(), i_D=data[bit], o_Q=local[bit])
                register.attr.add(('DONT_TOUCH', 'TRUE'))
                self.specials += register
            self.comb += slave.adr.eq(local)
