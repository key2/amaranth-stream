"""Routing components for amaranth-stream.

Provides :class:`StreamMux`, :class:`StreamDemux`, :class:`StreamGate`,
:class:`StreamSplitter`, and :class:`StreamJoiner` for routing streams
between multiple sources and sinks.
"""

from amaranth import *
from amaranth.hdl import Signal, ClockDomain, unsigned
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.utils import bits_for

from ._base import Signature as StreamSignature

__all__ = ["StreamMux", "StreamDemux", "StreamGate", "StreamSplitter", "StreamJoiner"]


def _get_forward_signals(sig):
    """Return the list of forward signal names for a stream signature.

    Forward signals are those driven by the source: payload, valid,
    and optionally first, last, param, keep.
    """
    names = ["payload"]
    if sig.has_first_last:
        names.extend(["first", "last"])
    if sig.param_shape is not None:
        names.append("param")
    if sig.has_keep:
        names.append("keep")
    return names


class StreamMux(wiring.Component):
    """N:1 multiplexer. Selects one of N inputs via ``sel``.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (identical for all ports).
    n : :class:`int`
        Number of input streams.

    Ports
    -----
    i_stream__0 .. i_stream__N-1 : In(signature)
        Input streams.
    o_stream : Out(signature)
        Output stream.
    sel : In(range(n))
        Selects which input to route to the output.
    """

    def __init__(self, signature, n):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        self._stream_sig = signature
        self._n = n

        members = {}
        for i in range(n):
            members[f"i_stream__{i}"] = In(signature)
        members["o_stream"] = Out(signature)
        members["sel"] = In(unsigned(bits_for(max(n - 1, 1))))
        super().__init__(members)

    @property
    def n(self):
        return self._n

    def get_input(self, i):
        """Return the i-th input stream interface."""
        return getattr(self, f"i_stream__{i}")

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)

        with m.Switch(self.sel):
            for i in range(self._n):
                with m.Case(i):
                    stream_i = self.get_input(i)
                    # Forward signals from selected input to output
                    for name in fwd_names:
                        m.d.comb += getattr(self.o_stream, name).eq(
                            getattr(stream_i, name))
                    m.d.comb += [
                        self.o_stream.valid.eq(stream_i.valid),
                        stream_i.ready.eq(self.o_stream.ready),
                    ]

        # Ensure non-selected inputs have ready=0
        # (The Switch above only drives ready for the selected input;
        #  Amaranth defaults undriven signals to 0, but let's be explicit
        #  for clarity in case of default handling.)

        return m


class StreamDemux(wiring.Component):
    """1:N demultiplexer. Routes input to one of N outputs via ``sel``.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (identical for all ports).
    n : :class:`int`
        Number of output streams.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream__0 .. o_stream__N-1 : Out(signature)
        Output streams.
    sel : In(range(n))
        Selects which output receives the input data.
    """

    def __init__(self, signature, n):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        self._stream_sig = signature
        self._n = n

        members = {}
        members["i_stream"] = In(signature)
        for i in range(n):
            members[f"o_stream__{i}"] = Out(signature)
        members["sel"] = In(unsigned(bits_for(max(n - 1, 1))))
        super().__init__(members)

    @property
    def n(self):
        return self._n

    def get_output(self, i):
        """Return the i-th output stream interface."""
        return getattr(self, f"o_stream__{i}")

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)

        # Drive all outputs with input payload/sideband (but only selected gets valid)
        for i in range(self._n):
            out = self.get_output(i)
            for name in fwd_names:
                m.d.comb += getattr(out, name).eq(
                    getattr(self.i_stream, name))

        # Only the selected output gets valid; ready comes from selected output
        with m.Switch(self.sel):
            for i in range(self._n):
                with m.Case(i):
                    out = self.get_output(i)
                    m.d.comb += [
                        out.valid.eq(self.i_stream.valid),
                        self.i_stream.ready.eq(out.ready),
                    ]

        return m


class StreamGate(wiring.Component):
    """Enable/disable gate for a stream.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    discard : :class:`bool`
        If ``True``, consume and discard data when gated (``en=0``).
        If ``False`` (default), apply backpressure when gated.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream.
    en : In(1)
        Enable signal. When high, stream passes through.
    """

    def __init__(self, signature, discard=False):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        self._stream_sig = signature
        self._discard = bool(discard)
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
            "en": In(1),
        })

    @property
    def discard(self):
        return self._discard

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)

        # Always forward payload/sideband signals
        for name in fwd_names:
            m.d.comb += getattr(self.o_stream, name).eq(
                getattr(self.i_stream, name))

        with m.If(self.en):
            # Pass through: wire valid and ready
            m.d.comb += [
                self.o_stream.valid.eq(self.i_stream.valid),
                self.i_stream.ready.eq(self.o_stream.ready),
            ]
        with m.Else():
            # Gated: output valid is 0
            m.d.comb += self.o_stream.valid.eq(0)
            if self._discard:
                # Discard mode: consume input (assert ready)
                m.d.comb += self.i_stream.ready.eq(1)
            else:
                # Backpressure mode: don't accept input (deassert ready)
                m.d.comb += self.i_stream.ready.eq(0)

        return m


class StreamSplitter(wiring.Component):
    """1:N broadcast/fanout. Synchronized — transfer only when ALL outputs ready.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (identical for all ports).
    n : :class:`int`
        Number of output streams.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream__0 .. o_stream__N-1 : Out(signature)
        Output streams (all receive the same data).
    """

    def __init__(self, signature, n):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        self._stream_sig = signature
        self._n = n

        members = {}
        members["i_stream"] = In(signature)
        for i in range(n):
            members[f"o_stream__{i}"] = Out(signature)
        super().__init__(members)

    @property
    def n(self):
        return self._n

    def get_output(self, i):
        """Return the i-th output stream interface."""
        return getattr(self, f"o_stream__{i}")

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)

        # Compute all_ready = AND of all output ready signals
        all_ready = Signal(name="all_ready")
        if self._n == 1:
            m.d.comb += all_ready.eq(self.get_output(0).ready)
        else:
            m.d.comb += all_ready.eq(
                Cat(*[self.get_output(i).ready for i in range(self._n)]).all()
            )

        # Input ready when all outputs are ready
        m.d.comb += self.i_stream.ready.eq(all_ready)

        # All outputs get the same data and valid
        for i in range(self._n):
            out = self.get_output(i)
            for name in fwd_names:
                m.d.comb += getattr(out, name).eq(
                    getattr(self.i_stream, name))
            m.d.comb += out.valid.eq(self.i_stream.valid & all_ready)

        return m


class StreamJoiner(wiring.Component):
    """N:1 interleaved join. Round-robin combining of N inputs.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (identical for all ports).
    n : :class:`int`
        Number of input streams.

    Ports
    -----
    i_stream__0 .. i_stream__N-1 : In(signature)
        Input streams.
    o_stream : Out(signature)
        Output stream.
    """

    def __init__(self, signature, n):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        self._stream_sig = signature
        self._n = n

        members = {}
        for i in range(n):
            members[f"i_stream__{i}"] = In(signature)
        members["o_stream"] = Out(signature)
        super().__init__(members)

    @property
    def n(self):
        return self._n

    def get_input(self, i):
        """Return the i-th input stream interface."""
        return getattr(self, f"i_stream__{i}")

    def elaborate(self, platform):
        m = Module()
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)

        # Round-robin counter
        sel = Signal(unsigned(bits_for(max(self._n - 1, 1))), name="rr_sel")

        # Connect current input to output based on sel
        with m.Switch(sel):
            for i in range(self._n):
                with m.Case(i):
                    stream_i = self.get_input(i)
                    for name in fwd_names:
                        m.d.comb += getattr(self.o_stream, name).eq(
                            getattr(stream_i, name))
                    m.d.comb += [
                        self.o_stream.valid.eq(stream_i.valid),
                        stream_i.ready.eq(self.o_stream.ready),
                    ]

        # Advance round-robin on successful transfer
        transfer = Signal(name="transfer")
        m.d.comb += transfer.eq(self.o_stream.valid & self.o_stream.ready)

        with m.If(transfer):
            if self._n == 1:
                m.d.sync += sel.eq(0)
            else:
                with m.If(sel == self._n - 1):
                    m.d.sync += sel.eq(0)
                with m.Else():
                    m.d.sync += sel.eq(sel + 1)

        return m
