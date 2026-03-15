"""Monitoring and debug components for amaranth-stream.

Provides :class:`StreamMonitor` for performance counters and
:class:`StreamChecker` for protocol assertion checking.
"""

from amaranth import *
from amaranth.hdl import Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ._base import Signature as StreamSignature

__all__ = ["StreamMonitor", "StreamChecker"]


class StreamMonitor(wiring.Component):
    """Performance counters: transfers, stalls, idles, packets. Tap-through.

    Passes all signals from ``i_stream`` to ``o_stream`` unchanged while
    counting various events.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    counter_width : :class:`int`
        Width of the performance counters (default 32).

    Ports
    -----
    i_stream : In(signature)
        Input stream (tap-through to o_stream).
    o_stream : Out(signature)
        Output stream (identical to i_stream).
    transfer_count : Out(counter_width)
        Number of completed transfers (valid & ready).
    stall_count : Out(counter_width)
        Number of stall cycles (valid & ~ready).
    idle_count : Out(counter_width)
        Number of idle cycles (~valid & ready).
    packet_count : Out(counter_width)
        Number of completed packets (valid & ready & last).
    clear : In(1)
        Reset all counters to 0.
    """

    def __init__(self, signature, counter_width=32):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        self._stream_sig = signature
        self._counter_width = counter_width
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
            "transfer_count": Out(counter_width),
            "stall_count": Out(counter_width),
            "idle_count": Out(counter_width),
            "packet_count": Out(counter_width),
            "clear": In(1),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig

        # Pass through all signals unchanged
        fwd_names = ["payload"]
        if sig.has_first_last:
            fwd_names.extend(["first", "last"])
        if sig.param_shape is not None:
            fwd_names.append("param")
        if sig.has_keep:
            fwd_names.append("keep")

        for name in fwd_names:
            m.d.comb += getattr(self.o_stream, name).eq(
                getattr(self.i_stream, name))
        m.d.comb += [
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Internal counters
        cw = self._counter_width
        transfer_cnt = Signal(cw, name="transfer_cnt")
        stall_cnt = Signal(cw, name="stall_cnt")
        idle_cnt = Signal(cw, name="idle_cnt")
        packet_cnt = Signal(cw, name="packet_cnt")

        # Handshake signals
        valid = self.i_stream.valid
        ready = self.o_stream.ready

        with m.If(self.clear):
            m.d.sync += [
                transfer_cnt.eq(0),
                stall_cnt.eq(0),
                idle_cnt.eq(0),
                packet_cnt.eq(0),
            ]
        with m.Else():
            # Transfer: valid & ready
            with m.If(valid & ready):
                m.d.sync += transfer_cnt.eq(transfer_cnt + 1)
            # Stall: valid & ~ready
            with m.If(valid & ~ready):
                m.d.sync += stall_cnt.eq(stall_cnt + 1)
            # Idle: ~valid & ready
            with m.If(~valid & ready):
                m.d.sync += idle_cnt.eq(idle_cnt + 1)
            # Packet: valid & ready & last (only if has_first_last)
            if sig.has_first_last:
                with m.If(valid & ready & self.i_stream.last):
                    m.d.sync += packet_cnt.eq(packet_cnt + 1)

        # Drive output ports
        m.d.comb += [
            self.transfer_count.eq(transfer_cnt),
            self.stall_count.eq(stall_cnt),
            self.idle_count.eq(idle_cnt),
            self.packet_count.eq(packet_cnt),
        ]

        return m


class StreamChecker(wiring.Component):
    """Protocol assertion checker for simulation.

    Monitors a stream for protocol violations:
    - Once ``valid`` is asserted, ``payload`` must not change until transfer.
    - Once ``valid`` is asserted, ``valid`` must not deassert until transfer.
    - If ``has_first_last``, ``first``/``last`` must not change while valid & ~ready.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature.

    Ports
    -----
    stream : In(signature)
        Stream to monitor (tap-only, does NOT drive ready).
    error : Out(1)
        Set to 1 if any protocol violation is detected.
    """

    def __init__(self, signature):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        self._stream_sig = signature
        super().__init__({
            "stream": In(signature),
            "error": Out(1),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig

        # Previous cycle values
        prev_valid = Signal(name="prev_valid")
        prev_payload = Signal(Shape.cast(sig.payload_shape).width, name="prev_payload")
        prev_ready = Signal(name="prev_ready")

        if sig.has_first_last:
            prev_first = Signal(name="prev_first")
            prev_last = Signal(name="prev_last")

        # Error flag (sticky)
        error_flag = Signal(name="error_flag")

        # Register previous values
        m.d.sync += [
            prev_valid.eq(self.stream.valid),
            prev_payload.eq(self.stream.payload),
            prev_ready.eq(self.stream.ready),
        ]
        if sig.has_first_last:
            m.d.sync += [
                prev_first.eq(self.stream.first),
                prev_last.eq(self.stream.last),
            ]

        # Previous cycle had a transfer?
        prev_transfer = Signal(name="prev_transfer")
        m.d.comb += prev_transfer.eq(prev_valid & prev_ready)

        # Check: valid was asserted last cycle, no transfer happened,
        # so valid must still be asserted this cycle
        with m.If(prev_valid & ~prev_transfer):
            # Valid must not deassert
            with m.If(~self.stream.valid):
                m.d.sync += error_flag.eq(1)
            # Payload must not change
            with m.If(self.stream.payload != prev_payload):
                m.d.sync += error_flag.eq(1)
            # first/last must not change
            if sig.has_first_last:
                with m.If(self.stream.first != prev_first):
                    m.d.sync += error_flag.eq(1)
                with m.If(self.stream.last != prev_last):
                    m.d.sync += error_flag.eq(1)

        m.d.comb += self.error.eq(error_flag)

        return m
