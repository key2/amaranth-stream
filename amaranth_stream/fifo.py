"""FIFO components with stream interfaces for amaranth-stream.

Provides :class:`StreamFIFO` (synchronous) and :class:`StreamAsyncFIFO`
(asynchronous / cross-domain) wrappers around Amaranth's built-in FIFO
primitives.
"""

import math

from amaranth import *
from amaranth.hdl import Shape
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib.fifo import SyncFIFO, SyncFIFOBuffered, AsyncFIFO, AsyncFIFOBuffered

from ._base import Signature as StreamSignature

__all__ = ["StreamFIFO", "StreamAsyncFIFO"]


def _stream_data_width(sig):
    """Calculate the total data width for packing all stream fields into a FIFO word.

    Returns (total_width, field_list) where field_list is a list of
    (name, width) tuples in packing order.
    """
    fields = []
    payload_width = Shape.cast(sig.payload_shape).width
    fields.append(("payload", payload_width))

    if sig.has_first_last:
        fields.append(("first", 1))
        fields.append(("last", 1))

    if sig.param_shape is not None:
        param_width = Shape.cast(sig.param_shape).width
        fields.append(("param", param_width))

    if sig.has_keep:
        keep_width = max(1, math.ceil(payload_width / 8))
        fields.append(("keep", keep_width))

    total_width = sum(w for _, w in fields)
    return total_width, fields


class StreamFIFO(wiring.Component):
    """Synchronous FIFO with stream interfaces.

    Packs all stream signals (payload, first, last, param, keep) into a
    single wide data word for storage in the underlying FIFO, and unpacks
    them on the read side.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    depth : :class:`int`
        FIFO depth in entries (≥0).
    buffered : :class:`bool`
        If ``True`` (default), uses :class:`SyncFIFOBuffered` (registered
        output, compatible with block RAM). If ``False``, uses
        :class:`SyncFIFO` (combinational output).

    Ports
    -----
    i_stream : In(signature)
        Input stream (write side).
    o_stream : Out(signature)
        Output stream (read side).
    level : Out(range(depth + 1))
        Number of entries currently in the FIFO.
    """

    def __init__(self, signature, depth, *, buffered=True):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not isinstance(depth, int) or depth < 0:
            raise ValueError(f"depth must be a non-negative integer, got {depth!r}")
        self._stream_sig = signature
        self._depth = depth
        self._buffered = bool(buffered)
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
            "level": Out(range(depth + 1)),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig
        total_width, fields = _stream_data_width(sig)

        # Instantiate the underlying FIFO
        if self._buffered:
            fifo = SyncFIFOBuffered(width=total_width, depth=self._depth)
        else:
            fifo = SyncFIFO(width=total_width, depth=self._depth)
        m.submodules.fifo = fifo

        # --- Write side: pack stream fields into FIFO data word ---
        pack_signals = []
        for name, _width in fields:
            pack_signals.append(getattr(self.i_stream, name))

        m.d.comb += [
            fifo.w_data.eq(Cat(*pack_signals)),
            fifo.w_en.eq(self.i_stream.valid & self.i_stream.ready),
            self.i_stream.ready.eq(fifo.w_rdy),
        ]

        # --- Read side: unpack FIFO data word into stream fields ---
        offset = 0
        for name, width in fields:
            m.d.comb += getattr(self.o_stream, name).eq(fifo.r_data[offset:offset + width])
            offset += width

        m.d.comb += [
            self.o_stream.valid.eq(fifo.r_rdy),
            fifo.r_en.eq(self.o_stream.valid & self.o_stream.ready),
        ]

        # --- Level ---
        m.d.comb += self.level.eq(fifo.level)

        return m


class StreamAsyncFIFO(wiring.Component):
    """Asynchronous (cross-domain) FIFO with stream interfaces.

    Packs all stream signals into a single wide data word, stores them
    in an :class:`AsyncFIFO` or :class:`AsyncFIFOBuffered`, and unpacks
    on the read side.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    depth : :class:`int`
        FIFO depth in entries. For :class:`AsyncFIFO`, this is rounded up
        to the next power of 2.
    w_domain : :class:`str`
        Write clock domain (default ``"write"``).
    r_domain : :class:`str`
        Read clock domain (default ``"read"``).
    buffered : :class:`bool`
        If ``True`` (default), uses :class:`AsyncFIFOBuffered`.
        If ``False``, uses :class:`AsyncFIFO`.

    Ports
    -----
    i_stream : In(signature)
        Input stream (in ``w_domain``).
    o_stream : Out(signature)
        Output stream (in ``r_domain``).
    """

    def __init__(self, signature, depth, *, w_domain="write", r_domain="read", buffered=True):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not isinstance(depth, int) or depth < 0:
            raise ValueError(f"depth must be a non-negative integer, got {depth!r}")
        self._stream_sig = signature
        self._depth = depth
        self._w_domain = w_domain
        self._r_domain = r_domain
        self._buffered = bool(buffered)
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig
        total_width, fields = _stream_data_width(sig)

        # Instantiate the underlying async FIFO
        if self._buffered:
            fifo = AsyncFIFOBuffered(
                width=total_width, depth=self._depth,
                w_domain=self._w_domain, r_domain=self._r_domain)
        else:
            fifo = AsyncFIFO(
                width=total_width, depth=self._depth,
                w_domain=self._w_domain, r_domain=self._r_domain)
        m.submodules.fifo = fifo

        # --- Write side: pack stream fields into FIFO data word ---
        pack_signals = []
        for name, _width in fields:
            pack_signals.append(getattr(self.i_stream, name))

        m.d.comb += [
            fifo.w_data.eq(Cat(*pack_signals)),
            fifo.w_en.eq(self.i_stream.valid & self.i_stream.ready),
            self.i_stream.ready.eq(fifo.w_rdy),
        ]

        # --- Read side: unpack FIFO data word into stream fields ---
        offset = 0
        for name, width in fields:
            m.d.comb += getattr(self.o_stream, name).eq(fifo.r_data[offset:offset + width])
            offset += width

        m.d.comb += [
            self.o_stream.valid.eq(fifo.r_rdy),
            fifo.r_en.eq(self.o_stream.valid & self.o_stream.ready),
        ]

        return m
