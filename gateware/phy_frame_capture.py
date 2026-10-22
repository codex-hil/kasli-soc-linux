# SPDX-License-Identifier: BSD-2-Clause
"""Passive bounded byte capture, using upstream LiteX CDC and Migen memory."""
from migen import Signal, If, Memory
from migen.genlib.cdc import PulseSynchronizer, MultiReg
from litex.gen import LiteXModule
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import CSRStorage, CSRStatus


class PHYFrameCapture(LiteXModule):
    def __init__(self, endpoint, domain, capacity=128):
        assert capacity == 128  # One complete 90-byte numbered Ethernet frame.
        self.arm = CSRStorage(1, name='arm')
        self.address = CSRStorage(8, name='address')
        self.data = CSRStatus(32, name='data')
        self.done = CSRStatus(1, name='done')
        self.length = CSRStatus(32, name='length')
        self.error = CSRStatus(1, name='error')
        self.overflow = CSRStatus(1, name='overflow')
        self.armed = CSRStatus(1, name='armed')
        self.capacity = CSRStatus(32, reset=capacity, name='capacity')
        self.trigger = PulseSynchronizer('sys', domain)
        self.comb += self.trigger.i.eq(self.arm.re & self.arm.storage)
        self.cdc = stream.ClockDomainCrossing([('data', 8), ('error', 1)],
            cd_from=domain, cd_to='sys', depth=256, buffered=True)
        active = Signal()
        in_frame = Signal()
        skip = Signal()
        lost = Signal()
        accepted = endpoint.valid & endpoint.ready
        # Observe traffic; never drive the monitored endpoint's ready/valid.
        self.comb += [self.cdc.sink.valid.eq(active & ~skip & accepted),
            self.cdc.sink.data.eq(endpoint.data),
            self.cdc.sink.error.eq(endpoint.error),
            self.cdc.sink.last.eq(endpoint.last), self.cdc.source.ready.eq(1)]
        getattr(self.sync, domain).__iadd__([
            If(accepted, in_frame.eq(~endpoint.last)),
            If(self.trigger.o,
                active.eq(1), skip.eq((in_frame | accepted) & ~(accepted & endpoint.last)), lost.eq(0)
            ).Elif(active & accepted,
                If(skip,
                    If(endpoint.last, skip.eq(0))
                ).Else(
                    If(~self.cdc.sink.ready, lost.eq(1)),
                    If(endpoint.last, active.eq(0))))])
        self.specials += [MultiReg(active, self.armed.status),
                          MultiReg(lost, self.overflow.status)]
        memory = Memory(8, capacity)
        writer = memory.get_port(write_capable=True)
        reader = memory.get_port(async_read=True)
        self.specials += [memory, writer, reader]
        count = Signal(16)
        bad = Signal()
        self.comb += [writer.adr.eq(count[:7]), writer.dat_w.eq(self.cdc.source.data),
            writer.we.eq(self.cdc.source.valid & ~self.done.status & (count < capacity)),
            reader.adr.eq(self.address.storage[:7]),
            If(self.address.storage < capacity, self.data.status.eq(reader.dat_r))]
        self.sync += If(self.arm.re & self.arm.storage,
            self.done.status.eq(0), self.length.status.eq(0),
            self.error.status.eq(0), count.eq(0), bad.eq(0)
        ).Elif(self.cdc.source.valid & ~self.done.status,
            count.eq(count + 1), bad.eq(bad | self.cdc.source.error),
            If(self.cdc.source.last,
                self.done.status.eq(1), self.length.status.eq(count + 1),
                self.error.status.eq(bad | self.cdc.source.error)))
