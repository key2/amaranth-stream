"""Data transformation components for amaranth-stream.

Provides :class:`StreamMap`, :class:`StreamFilter`, :class:`EndianSwap`,
and :class:`ByteAligner` for transforming stream payloads.
"""

import math

from amaranth import *
from amaranth.hdl import Signal, Shape, Cat, Mux, ClockDomain
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ._base import Signature as StreamSignature

__all__ = ["StreamMap", "StreamFilter", "EndianSwap", "ByteAligner"]


def _get_forward_signals(sig):
    """Return the list of forward signal names (excluding payload and valid)."""
    names = []
    if sig.has_first_last:
        names.extend(["first", "last"])
    if sig.param_shape is not None:
        names.append("param")
    if sig.has_keep:
        names.append("keep")
    return names


class StreamMap(wiring.Component):
    """Combinational payload transformation via user-provided function.

    Parameters
    ----------
    i_signature : :class:`~amaranth_stream.Signature`
        Input stream signature.
    o_signature : :class:`~amaranth_stream.Signature`
        Output stream signature.
    transform : callable
        ``transform(m, payload_in)`` → payload expression for output.
        Called during :meth:`elaborate` to create combinational logic.

    Ports
    -----
    i_stream : In(i_signature)
        Input stream.
    o_stream : Out(o_signature)
        Output stream with transformed payload.
    """

    def __init__(self, i_signature, o_signature, transform):
        if not isinstance(i_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature for i_signature, "
                f"got {type(i_signature).__name__}")
        if not isinstance(o_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature for o_signature, "
                f"got {type(o_signature).__name__}")
        self._i_sig = i_signature
        self._o_sig = o_signature
        self._transform = transform
        super().__init__({
            "i_stream": In(i_signature),
            "o_stream": Out(o_signature),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        # Apply the user-provided transform to get the output payload expression
        transformed = self._transform(m, self.i_stream.payload)

        m.d.comb += [
            self.o_stream.payload.eq(transformed),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Pass through optional signals that exist on both sides
        if self._i_sig.has_first_last and self._o_sig.has_first_last:
            m.d.comb += [
                self.o_stream.first.eq(self.i_stream.first),
                self.o_stream.last.eq(self.i_stream.last),
            ]
        if self._i_sig.param_shape is not None and self._o_sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)
        if self._i_sig.has_keep and self._o_sig.has_keep:
            m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)

        return m


class StreamFilter(wiring.Component):
    """Conditional beat dropping via user-provided predicate.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    predicate : callable
        ``predicate(m, payload)`` → Signal(1). Returns 1 to pass, 0 to drop.
        Called during :meth:`elaborate`.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream (dropped beats are consumed but not forwarded).
    """

    def __init__(self, signature, predicate):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        self._stream_sig = signature
        self._predicate = predicate
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        pass_signal = self._predicate(m, self.i_stream.payload)

        m.d.comb += [
            self.o_stream.payload.eq(self.i_stream.payload),
            self.o_stream.valid.eq(self.i_stream.valid & pass_signal),
            self.i_stream.ready.eq(Mux(pass_signal, self.o_stream.ready, 1)),
        ]

        # Pass through optional signals
        fwd = _get_forward_signals(self._stream_sig)
        for name in fwd:
            m.d.comb += getattr(self.o_stream, name).eq(
                getattr(self.i_stream, name))

        return m


class EndianSwap(wiring.Component):
    """Byte-order reversal. Payload must be a multiple of 8 bits.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature. Payload width must be a multiple of 8.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream with reversed byte order.
    """

    def __init__(self, signature):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        pw = signature.payload_width
        if pw % 8 != 0:
            raise ValueError(
                f"Payload width must be a multiple of 8, got {pw}")
        self._stream_sig = signature
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        pw = self._stream_sig.payload_width
        n_bytes = pw // 8

        # Reverse byte order
        bytes_reversed = []
        for i in range(n_bytes):
            bytes_reversed.append(self.i_stream.payload[i * 8:(i + 1) * 8])
        bytes_reversed.reverse()

        m.d.comb += [
            self.o_stream.payload.eq(Cat(*bytes_reversed)),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Pass through optional signals
        fwd = _get_forward_signals(self._stream_sig)
        for name in fwd:
            m.d.comb += getattr(self.o_stream, name).eq(
                getattr(self.i_stream, name))

        return m


class ByteAligner(wiring.Component):
    """Sub-word byte alignment with configurable shift.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature.
    max_shift : :class:`int`
        Maximum shift in bytes.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream with shifted payload.
    shift : In(range(max_shift + 1))
        Number of bytes to shift left.
    """

    def __init__(self, signature, max_shift):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if max_shift < 1:
            raise ValueError(f"max_shift must be >= 1, got {max_shift}")
        self._stream_sig = signature
        self._max_shift = max_shift
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
            "shift": In(range(max_shift + 1)),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        pw = self._stream_sig.payload_width

        # Barrel shifter: shift left by shift * 8 bits
        shifted = Signal(pw, name="shifted")
        m.d.comb += shifted.eq(self.i_stream.payload << (self.shift * 8))

        m.d.comb += [
            self.o_stream.payload.eq(shifted),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Pass through optional signals
        if self._stream_sig.has_first_last:
            m.d.comb += [
                self.o_stream.first.eq(self.i_stream.first),
                self.o_stream.last.eq(self.i_stream.last),
            ]
        if self._stream_sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)
        if self._stream_sig.has_keep:
            m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)

        return m
