"""Monitoring and debug components for amaranth-stream.

Provides :class:`StreamMonitor` for performance counters,
:class:`StreamChecker` for protocol assertion checking, and
:class:`StreamProtocolChecker` for protocol violation detection with error codes.
"""

from amaranth import *
from amaranth.hdl import Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ._base import Signature as StreamSignature

__all__ = ["StreamMonitor", "StreamChecker", "StreamProtocolChecker"]


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


class StreamProtocolChecker(wiring.Component):
    """Protocol checker with error codes for stream protocol violations.

    Passively monitors a stream and reports protocol violations with
    specific error codes.  The checker does not drive ``ready`` or
    ``valid`` — it is purely an observer.

    Protocol checks
    ---------------
    1. **first without preceding last** — ``first`` must not be asserted
       unless the previous transfer had ``last=1`` or this is the very
       first transfer.  (Only checked when the signature has first/last.)
    2. **valid deasserted without handshake** — once ``valid`` is asserted,
       it must remain asserted until a transfer (``valid & ready``) occurs.
    3. **payload changed without handshake** — while ``valid=1`` and
       ``ready=0``, the payload must remain stable.

    Error codes
    -----------
    0 = no error,
    1 = first without preceding last,
    2 = valid deasserted without handshake,
    3 = payload changed without handshake.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature to monitor.
    domain : :class:`str`
        Clock domain (default ``"sync"``).

    Ports
    -----
    stream : In(signature)
        Stream to monitor (passive — does NOT drive ready).
    error : Out(1)
        Asserted when a protocol violation is detected this cycle.
    error_code : Out(2)
        Indicates which violation occurred (0–3).
    """

    def __init__(self, signature, domain="sync"):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        self._stream_sig = signature
        self._domain = domain
        super().__init__({
            "stream": In(signature),
            "error": Out(1),
            "error_code": Out(2),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig
        domain = self._domain

        # Previous-cycle registers
        prev_valid = Signal(name="prev_valid")
        prev_ready = Signal(name="prev_ready")
        prev_payload = Signal(Shape.cast(sig.payload_shape).width, name="prev_payload")

        # Register previous-cycle values
        m.d[domain] += [
            prev_valid.eq(self.stream.valid),
            prev_ready.eq(self.stream.ready),
            prev_payload.eq(self.stream.payload),
        ]

        # For first/last checking, we need additional registers
        if sig.has_first_last:
            prev_first = Signal(name="prev_first")
            # Tracks whether the last completed transfer had last=1.
            # Initialised to 1 so the very first transfer may assert first.
            last_xfer_had_last = Signal(name="last_xfer_had_last", init=1)
            # Delayed copy: holds last_xfer_had_last from the previous cycle
            # (before the current transfer updated it).
            prev_xfer_had_last = Signal(name="prev_xfer_had_last", init=1)

            m.d[domain] += [
                prev_first.eq(self.stream.first),
                prev_xfer_had_last.eq(last_xfer_had_last),
            ]
            # Update last_xfer_had_last on every completed transfer
            with m.If(self.stream.valid & self.stream.ready):
                m.d[domain] += last_xfer_had_last.eq(self.stream.last)

        # Error detection (active for one cycle per violation)
        error = Signal(name="error_out")
        error_code = Signal(2, name="error_code_out")

        # Previous cycle had valid=1 but no transfer (valid & ~ready)
        prev_stall = Signal(name="prev_stall")
        m.d.comb += prev_stall.eq(prev_valid & ~prev_ready)

        # Previous cycle had a completed transfer
        prev_transfer = Signal(name="prev_transfer")
        m.d.comb += prev_transfer.eq(prev_valid & prev_ready)

        # Build the condition for check 1 (first without last).
        # When has_first_last is False, first_err is always 0 (never fires).
        if sig.has_first_last:
            # If the previous cycle was a transfer with first=1, the
            # transfer before it must have had last=1.
            first_err = Signal(name="first_err")
            m.d.comb += first_err.eq(
                prev_transfer & prev_first & ~prev_xfer_had_last)
        else:
            first_err = Const(0)

        # Priority-encoded error checks (only one error reported per cycle)
        with m.If(prev_stall & ~self.stream.valid):
            # Check 2: valid deasserted without handshake
            m.d.comb += [
                error.eq(1),
                error_code.eq(2),
            ]
        with m.Elif(prev_stall & (self.stream.payload != prev_payload)):
            # Check 3: payload changed without handshake
            m.d.comb += [
                error.eq(1),
                error_code.eq(3),
            ]
        with m.Elif(first_err):
            # Check 1: first without preceding last
            m.d.comb += [
                error.eq(1),
                error_code.eq(1),
            ]

        # Drive output ports
        m.d.comb += [
            self.error.eq(error),
            self.error_code.eq(error_code),
        ]

        return m
