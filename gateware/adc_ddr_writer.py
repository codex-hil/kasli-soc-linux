#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Finite, loss-detecting ADC capture through an independent asynchronous FIFO.

Eight 64-bit sample ticks form one native 512-bit DRAM word. No sample
backpressure is possible: a full FIFO sets a sticky failure, never hides loss.
CSR configuration is held throughout the request/acknowledgement handshake.
"""
from migen import Cat, If, Signal
from migen.genlib.cdc import MultiReg
from litex.gen import LiteXModule
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import CSR, CSRStatus, CSRStorage
from litedram.frontend.dma import LiteDRAMDMAWriter


class ADCToDDR(LiteXModule):
    def __init__(self, port, samples, aligned, frame, domain, card, fifo_depth=256):
        assert port.data_width == 512
        self.base = CSRStorage(30, name='base')  # byte offset in the PL SODIMM
        self.length = CSRStorage(27, name='length')  # 64-bit sample ticks, multiple of 8
        self.synthetic = CSRStorage(name='synthetic')
        self.start = CSR(name='start')
        self.status = CSRStatus(5, name='status')  # busy, done, overflow, frame bad, config bad
        self.written = CSRStatus(27, name='written')
        self.dropped = CSRStatus(27, name='dropped')
        self.ticks = CSRStatus(32, name='ticks')  # system clock cycles, including drain
        self.signature = CSRStatus(32, reset=0x41444452, name='signature')
        self.fifo = stream.ClockDomainCrossing([('data', 512)],
            cd_from=domain, cd_to='sys', depth=fifo_depth, buffered=True,
            with_common_rst=True)
        self.writer = LiteDRAMDMAWriter(port, fifo_depth=16, fifo_buffered=True)
        # Break native DDR command-ready feedback before the async FIFO BRAM address.
        self.output_buffer = stream.Buffer(self.fifo.source.description,
            pipe_valid=True, pipe_ready=True)
        self.comb += self.fifo.source.connect(self.output_buffer.sink)

        request, request_adc, ack, ack_sys = [Signal() for _ in range(4)]
        busy, done, config_bad = Signal(), Signal(), Signal()
        overflow, frame_bad, active = Signal(), Signal(), Signal()
        overflow_sys, frame_bad_sys = Signal(), Signal()
        size_adc, synthetic_adc = Signal(27), Signal()
        size_latched, synthetic_latched, busy_adc = Signal(27), Signal(), Signal()
        dropped_adc, dropped_sys = Signal(27), Signal(27)
        self.specials += [MultiReg(request, request_adc, domain), MultiReg(ack, ack_sys),
            MultiReg(size_latched, size_adc, domain),
            MultiReg(synthetic_latched, synthetic_adc, domain), MultiReg(busy, busy_adc, domain),
            MultiReg(overflow, overflow_sys), MultiReg(frame_bad, frame_bad_sys),
            MultiReg(dropped_adc, dropped_sys)]
        # dropped is consumed only after ack and an additional settling interval.
        pack = Signal(512)
        count = Signal(27)
        incoming = Signal(64)
        self.comb += incoming.eq(samples)
        # count is widened explicitly so the diagnostic layout is two 32-bit words.
        diagnostic_count = Signal(32)
        self.comb += diagnostic_count.eq(count)
        self.comb += If(synthetic_adc,
            incoming.eq(Cat(diagnostic_count, diagnostic_count ^ (0xadc00000 + card))))
        packed = Cat(pack[64:], incoming)
        self.comb += [self.fifo.sink.valid.eq(active & (count[:3] == 7)),
                      self.fifo.sink.data.eq(packed)]
        adc_sync = getattr(self.sync, domain)
        adc_sync += If(~busy_adc, active.eq(0), ack.eq(request_adc)).Elif(~active & (request_adc != ack),
            active.eq(1), count.eq(0), pack.eq(0), dropped_adc.eq(0),
            overflow.eq(0), frame_bad.eq(0)
        ).Elif(active,
            pack.eq(packed), count.eq(count + 1),
            If(~aligned | (frame != 0x0f), frame_bad.eq(1)),
            If((count[:3] == 7) & ~self.fifo.sink.ready,
                overflow.eq(1), dropped_adc.eq(dropped_adc + 8)),
            If(count == size_adc - 1, active.eq(0), ack.eq(request_adc))
        )

        words = Signal(24)
        base_word = Signal(port.address_width)
        settling = Signal(4)
        launching = Signal(4)
        empty = Signal()
        self.comb += empty.eq(~self.fifo.source.valid & ~self.output_buffer.source.valid & ~self.writer.fifo.source.valid)
        self.comb += [self.writer.sink.valid.eq(busy & self.output_buffer.source.valid),
            self.writer.sink.data.eq(self.output_buffer.source.data),
            self.writer.sink.address.eq(base_word + words),
            self.output_buffer.source.ready.eq(busy & self.writer.sink.ready),
            self.status.status.eq(Cat(busy, done, overflow_sys, frame_bad_sys, config_bad)),
            self.written.status.eq(words << 3)]
        # Widen the span/end calculation: no wrapped range can pass the check.
        end = Signal(34)
        self.comb += end.eq(self.base.storage + (self.length.storage << 3))
        self.sync += If(self.start.re & ~busy,
            done.eq(0), config_bad.eq(0), self.ticks.status.eq(0),
            If((self.base.storage[:6] != 0) | (self.length.storage == 0)
                | (self.length.storage[:3] != 0) | (end > 0x40000000) | ~empty,
                config_bad.eq(1), done.eq(1)
            ).Else(
                base_word.eq(self.base.storage[6:]), words.eq(0),
                settling.eq(0), launching.eq(0), busy.eq(1),
                size_latched.eq(self.length.storage), synthetic_latched.eq(self.synthetic.storage)
            )
        ).Elif(busy,
            self.ticks.status.eq(self.ticks.status + 1),
            If(self.writer.sink.valid & self.writer.sink.ready, words.eq(words + 1)),
            If(launching != 8,
                launching.eq(launching + 1),
                If(launching == 7, request.eq(~request))
            ).Elif(ack_sys == request,
                If(settling != 15, settling.eq(settling + 1)).Elif(empty,
                    busy.eq(0), done.eq(1), self.dropped.status.eq(dropped_sys))
            ).Else(settling.eq(0))
        )
