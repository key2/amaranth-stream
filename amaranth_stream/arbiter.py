"""Arbitration components for amaranth-stream.

Provides :class:`StreamArbiter` (packet-aware N:1 arbiter) and
:class:`StreamDispatcher` (packet-aware 1:N dispatcher).
"""

from amaranth import *
from amaranth.hdl import Signal, ClockDomain, unsigned, Cat, Array
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.utils import bits_for

from ._base import Signature as StreamSignature

__all__ = ["StreamArbiter", "StreamDispatcher"]


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


class StreamArbiter(wiring.Component):
    """Packet-aware N:1 arbiter. Holds grant until last.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (must have ``has_first_last=True``).
    n : :class:`int`
        Number of input streams.
    round_robin : :class:`bool`
        If ``True`` (default), use round-robin arbitration.
        If ``False``, use priority arbitration (lower index = higher priority).

    Ports
    -----
    i_stream__0 .. i_stream__N-1 : In(signature)
        Input streams.
    o_stream : Out(signature)
        Output stream.
    grant : Out(range(n))
        Currently granted input index.
    """

    def __init__(self, signature, n, *, round_robin=True):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not signature.has_first_last:
            raise ValueError("StreamArbiter requires a signature with has_first_last=True")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        self._stream_sig = signature
        self._n = n
        self._round_robin = bool(round_robin)

        members = {}
        for i in range(n):
            members[f"i_stream__{i}"] = In(signature)
        members["o_stream"] = Out(signature)
        members["grant"] = Out(unsigned(bits_for(max(n - 1, 1))))
        super().__init__(members)

    @property
    def n(self):
        return self._n

    @property
    def round_robin(self):
        return self._round_robin

    def get_input(self, i):
        """Return the i-th input stream interface."""
        return getattr(self, f"i_stream__{i}")

    def elaborate(self, platform):
        m = Module()
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)
        n = self._n

        # State
        locked = Signal(name="locked")
        grant_reg = Signal(unsigned(bits_for(max(n - 1, 1))), name="grant_reg")
        last_grant = Signal(unsigned(bits_for(max(n - 1, 1))), name="last_grant")

        # Compute next grant using round-robin or priority
        # For round-robin, we need to find the next valid input after last_grant
        # We pre-compute a "request" vector
        request = Signal(n, name="request")
        for i in range(n):
            m.d.comb += request[i].eq(self.get_input(i).valid)

        # Next grant selection
        next_grant = Signal(unsigned(bits_for(max(n - 1, 1))), name="next_grant")
        next_valid = Signal(name="next_valid")

        if self._round_robin:
            # Round-robin priority encoder
            # Create a doubled request vector shifted by (last_grant + 1)
            # Then find the first set bit
            # Simpler approach: for each possible last_grant value, hardcode the priority order
            m.d.comb += next_valid.eq(0)
            m.d.comb += next_grant.eq(0)

            if n == 1:
                m.d.comb += next_valid.eq(request[0])
                m.d.comb += next_grant.eq(0)
            else:
                # For each possible value of last_grant, determine priority order
                with m.Switch(last_grant):
                    for lg in range(n):
                        with m.Case(lg):
                            # Priority order: lg+1, lg+2, ..., n-1, 0, 1, ..., lg
                            # Use reversed order so first valid (highest priority) wins
                            # (last assignment wins in Amaranth comb)
                            for offset in reversed(range(n)):
                                idx = (lg + 1 + offset) % n
                                with m.If(request[idx]):
                                    m.d.comb += next_grant.eq(idx)
                                    m.d.comb += next_valid.eq(1)
        else:
            # Priority: lower index = higher priority
            m.d.comb += next_valid.eq(0)
            m.d.comb += next_grant.eq(0)
            # Reversed so lower index wins (last assignment wins)
            for i in reversed(range(n)):
                with m.If(request[i]):
                    m.d.comb += next_grant.eq(i)
                    m.d.comb += next_valid.eq(1)

        # Effective grant
        eff_grant = Signal(unsigned(bits_for(max(n - 1, 1))), name="eff_grant")
        eff_valid = Signal(name="eff_valid")

        with m.If(locked):
            m.d.comb += eff_grant.eq(grant_reg)
            m.d.comb += eff_valid.eq(1)
        with m.Else():
            m.d.comb += eff_grant.eq(next_grant)
            m.d.comb += eff_valid.eq(next_valid)

        # Drive grant output
        m.d.comb += self.grant.eq(eff_grant)

        # Connect selected input to output
        for i in range(n):
            stream_i = self.get_input(i)
            with m.If((eff_grant == i) & eff_valid):
                for name in fwd_names:
                    m.d.comb += getattr(self.o_stream, name).eq(
                        getattr(stream_i, name))
                m.d.comb += [
                    self.o_stream.valid.eq(stream_i.valid),
                    stream_i.ready.eq(self.o_stream.ready),
                ]

        # Transfer detection
        transfer = Signal(name="transfer")
        m.d.comb += transfer.eq(self.o_stream.valid & self.o_stream.ready)

        # Lock/unlock logic
        with m.If(transfer):
            with m.If(~locked):
                with m.If(self.o_stream.first & ~self.o_stream.last):
                    m.d.sync += locked.eq(1)
                    m.d.sync += grant_reg.eq(eff_grant)
                m.d.sync += last_grant.eq(eff_grant)
            with m.Else():
                with m.If(self.o_stream.last):
                    m.d.sync += locked.eq(0)
                    m.d.sync += last_grant.eq(grant_reg)

        return m


class StreamDispatcher(wiring.Component):
    """Packet-aware 1:N dispatcher. Latches sel on first, holds until last.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (must have ``has_first_last=True``).
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
        Latched on first beat of a packet.
    """

    def __init__(self, signature, n):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not signature.has_first_last:
            raise ValueError("StreamDispatcher requires a signature with has_first_last=True")
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
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)
        n = self._n

        # State: locked means we're in the middle of a packet
        locked = Signal(name="locked")
        latched_sel = Signal(unsigned(bits_for(max(n - 1, 1))), name="latched_sel")

        # Effective sel: use latched value when locked, otherwise current sel
        eff_sel = Signal(unsigned(bits_for(max(n - 1, 1))), name="eff_sel")
        with m.If(locked):
            m.d.comb += eff_sel.eq(latched_sel)
        with m.Else():
            m.d.comb += eff_sel.eq(self.sel)

        # Drive all outputs with input payload/sideband (but only selected gets valid)
        for i in range(n):
            out = self.get_output(i)
            for name in fwd_names:
                m.d.comb += getattr(out, name).eq(
                    getattr(self.i_stream, name))

        # Only the selected output gets valid; ready comes from selected output
        for i in range(n):
            out = self.get_output(i)
            with m.If(eff_sel == i):
                m.d.comb += [
                    out.valid.eq(self.i_stream.valid),
                    self.i_stream.ready.eq(out.ready),
                ]

        # Transfer detection
        transfer = Signal(name="transfer")
        m.d.comb += transfer.eq(self.i_stream.valid & self.i_stream.ready)

        # Lock/unlock logic
        with m.If(transfer):
            with m.If(~locked):
                with m.If(self.i_stream.first & ~self.i_stream.last):
                    m.d.sync += locked.eq(1)
                    m.d.sync += latched_sel.eq(eff_sel)
            with m.Else():
                with m.If(self.i_stream.last):
                    m.d.sync += locked.eq(0)

        return m
