#!/usr/bin/env python3
"""Cycle-equivalence of original and replicated registered CSR transactions."""
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateware'))
from migen import Module, If, Instance, ClockDomain
from migen.sim import run_simulation
from litex.soc.interconnect import wishbone, csr_bus
from litex.soc.interconnect.csr import CSRStorage
from csr_address_replication import CSRAddressReplication


class FDREModel:
    @staticmethod
    def lower(instance):
        if instance.of != 'FDRE':
            raise ValueError(instance.of)
        signals = {item.name: item.expr for item in instance.items
                   if isinstance(item, (Instance.Input, Instance.Output))}
        model = Module()
        model.sync += If(signals['R'], signals['Q'].eq(0)).Elif(
            signals['CE'], signals['Q'].eq(signals['D']))
        return model


class BusPair(Module):
    def __init__(self):
        self.clock_domains.cd_sys = ClockDomain("sys")
        self.bridges, self.registers = [], []
        for replicated in (False, True):
            bridge = wishbone.Wishbone2CSR(
                wishbone.Interface(data_width=32),
                bus_csr=csr_bus.Interface(data_width=32, address_width=14), register=True)
            registers = [CSRStorage(32, name=f'scratch_{i}') for i in range(3)]
            banks = [csr_bus.CSRBank([reg], address=i, bus=csr_bus.Interface.like(bridge.csr))
                     for i, reg in enumerate(registers)]
            interconnect = csr_bus.InterconnectShared([bridge.csr], [b.bus for b in banks])
            self.submodules += [bridge, interconnect] + banks
            if replicated:
                self.submodules += CSRAddressReplication(bridge, interconnect, [b.bus for b in banks])
            self.bridges.append(bridge)
            self.registers.append(registers)


def check(seed):
    dut = BusPair()
    rng = random.Random(seed)
    def process():
        def compare():
            for field in ('ack', 'dat_r'):
                left = yield getattr(dut.bridges[0].wishbone, field)
                right = yield getattr(dut.bridges[1].wishbone, field)
                assert left == right, (seed, field, left, right)
            for left, right in zip(*dut.registers):
                a = yield left.storage
                b = yield right.storage
                assert a == b, (seed, a, b)
        for transaction in range(150):
            bank = rng.randrange(4)  # Includes an unmapped address.
            writing = rng.randrange(2)
            data = rng.getrandbits(32)
            sel = rng.choice([0, 1, 3, 15])
            if transaction % 23 == 0:
                yield dut.cd_sys.rst.eq(1)
                yield
                yield
                yield from compare()
                yield dut.cd_sys.rst.eq(0)
                yield
            for bridge in dut.bridges:
                wb = bridge.wishbone
                yield wb.adr.eq(bank*512)
                yield wb.dat_w.eq(data)
                yield wb.sel.eq(sel)
                yield wb.we.eq(writing)
                yield wb.cyc.eq(1)
                yield wb.stb.eq(1)
            for cycle in range(8):
                yield
                yield from compare()
                ack = yield dut.bridges[0].wishbone.ack
                if ack:
                    break
            else:
                raise AssertionError('CSR transaction timed out')
            for bridge in dut.bridges:
                yield bridge.wishbone.cyc.eq(0)
                yield bridge.wishbone.stb.eq(0)
            for _ in range(rng.randrange(1, 4)):
                yield
                yield from compare()
    run_simulation(dut, process(), special_overrides={Instance: FDREModel})


if __name__ == '__main__':
    for seed in (3, 19, 706):
        check(seed)
    print('PASS: 450 CSR transactions, cycle-exact ACK/read/storage equivalence')
