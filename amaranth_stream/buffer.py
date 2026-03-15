"""Pipeline buffer components for amaranth-stream.

Provides :class:`Buffer`, :class:`PipeValid`, :class:`PipeReady`, and
:class:`Delay` for breaking combinational paths and adding pipeline stages.
"""

from amaranth import *
from amaranth.hdl import Signal, ClockDomain
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, connect

from ._base import Signature as StreamSignature

__all__ = ["Buffer", "PipeValid", "PipeReady", "Delay"]


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


class Buffer(wiring.Component):
    """Pipeline register that breaks combinational paths.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    pipe_valid : :class:`bool`
        If ``True``, register the forward path (payload, valid, first, last,
        param, keep). Default ``True``.
    pipe_ready : :class:`bool`
        If ``True``, register the backward path (ready). Default ``True``.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream.
    """

    def __init__(self, signature, pipe_valid=True, pipe_ready=True):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        self._stream_sig = signature
        self._pipe_valid = bool(pipe_valid)
        self._pipe_ready = bool(pipe_ready)
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()

        if self._pipe_valid and self._pipe_ready:
            return self._elaborate_full(m)
        elif self._pipe_valid:
            return self._elaborate_pipe_valid(m)
        elif self._pipe_ready:
            return self._elaborate_pipe_ready(m)
        else:
            return self._elaborate_passthrough(m)

    def _elaborate_passthrough(self, m):
        """Wire-through: no registers."""
        m.domains += ClockDomain("sync")
        fwd_names = _get_forward_signals(self._stream_sig)
        for name in fwd_names:
            m.d.comb += getattr(self.o_stream, name).eq(
                getattr(self.i_stream, name))
        m.d.comb += [
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]
        return m

    def _elaborate_pipe_valid(self, m):
        """Forward-registered (skid buffer forward register).

        Registers payload, valid, first, last, param, keep.
        Ready is combinational pass-through.
        """
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)

        # Output valid register
        o_valid = Signal(init=0, name="o_valid")

        # Output registers for each forward signal
        o_regs = {}
        for name in fwd_names:
            o_regs[name] = Signal(
                getattr(self.i_stream, name).shape(),
                name=f"o_{name}")

        # When output is ready or output is not valid, capture input
        can_accept = Signal(name="can_accept")
        m.d.comb += can_accept.eq(self.o_stream.ready | ~o_valid)

        with m.If(can_accept):
            m.d.sync += o_valid.eq(self.i_stream.valid)
            for name in fwd_names:
                m.d.sync += o_regs[name].eq(getattr(self.i_stream, name))

        # Ready is combinational: accept when we can
        m.d.comb += self.i_stream.ready.eq(can_accept)

        # Drive output
        m.d.comb += self.o_stream.valid.eq(o_valid)
        for name in fwd_names:
            m.d.comb += getattr(self.o_stream, name).eq(o_regs[name])

        return m

    def _elaborate_pipe_ready(self, m):
        """Backward-registered (skid buffer backward register).

        Ready is registered. Forward path is combinational with a bypass
        register for when downstream was not ready.
        """
        sig = self._stream_sig
        fwd_names = _get_forward_signals(sig)

        # Buffer register for when downstream not ready
        buf_valid = Signal(init=0, name="buf_valid")
        buf_regs = {}
        for name in fwd_names:
            buf_regs[name] = Signal(
                getattr(self.i_stream, name).shape(),
                name=f"buf_{name}")

        # Capture into buffer when: input handshake happens but output not ready
        # i.e., we accepted data (ready was high) but downstream can't take it
        with m.If(self.i_stream.valid & self.i_stream.ready & ~self.o_stream.ready):
            m.d.sync += buf_valid.eq(1)
            for name in fwd_names:
                m.d.sync += buf_regs[name].eq(getattr(self.i_stream, name))
        with m.Elif(self.o_stream.ready):
            m.d.sync += buf_valid.eq(0)

        # Output mux: buffer takes priority
        with m.If(buf_valid):
            m.d.comb += self.o_stream.valid.eq(1)
            for name in fwd_names:
                m.d.comb += getattr(self.o_stream, name).eq(buf_regs[name])
        with m.Else():
            m.d.comb += self.o_stream.valid.eq(self.i_stream.valid)
            for name in fwd_names:
                m.d.comb += getattr(self.o_stream, name).eq(
                    getattr(self.i_stream, name))

        # Ready: accept if buffer is empty
        m.d.comb += self.i_stream.ready.eq(~buf_valid)

        return m

    def _elaborate_full(self, m):
        """Both paths registered: chain PipeValid then PipeReady."""
        sig = self._stream_sig

        # Create internal PipeValid and PipeReady stages
        pipe_v = PipeValid(sig)
        pipe_r = PipeReady(sig)
        m.submodules.pipe_v = pipe_v
        m.submodules.pipe_r = pipe_r

        # Connect: input -> PipeValid -> PipeReady -> output
        connect(m, wiring.flipped(self.i_stream), pipe_v.i_stream)
        connect(m, pipe_v.o_stream, pipe_r.i_stream)
        connect(m, pipe_r.o_stream, wiring.flipped(self.o_stream))

        return m


class PipeValid(Buffer):
    """Convenience wrapper: forward-registered pipeline stage.

    Registers payload, valid, first, last, param, keep.
    Ready is combinational pass-through.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    """

    def __init__(self, signature):
        super().__init__(signature, pipe_valid=True, pipe_ready=False)


class PipeReady(Buffer):
    """Convenience wrapper: backward-registered pipeline stage.

    Ready is registered. Forward path is combinational with a bypass register.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    """

    def __init__(self, signature):
        super().__init__(signature, pipe_valid=False, pipe_ready=True)


class Delay(wiring.Component):
    """N-stage pipeline delay using chained PipeValid stages.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    stages : :class:`int`
        Number of pipeline stages. 0 means wire-through. Default 1.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream.
    """

    def __init__(self, signature, stages=1):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if stages < 0:
            raise ValueError(f"stages must be >= 0, got {stages}")
        self._stream_sig = signature
        self._stages = stages
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()

        if self._stages == 0:
            # Wire-through
            m.domains += ClockDomain("sync")
            fwd_names = _get_forward_signals(self._stream_sig)
            for name in fwd_names:
                m.d.comb += getattr(self.o_stream, name).eq(
                    getattr(self.i_stream, name))
            m.d.comb += [
                self.o_stream.valid.eq(self.i_stream.valid),
                self.i_stream.ready.eq(self.o_stream.ready),
            ]
            return m

        # Create N PipeValid stages
        stages = []
        for i in range(self._stages):
            stage = PipeValid(self._stream_sig)
            m.submodules[f"stage_{i}"] = stage
            stages.append(stage)

        # Connect: input -> stage_0 -> stage_1 -> ... -> stage_N-1 -> output
        connect(m, wiring.flipped(self.i_stream), stages[0].i_stream)
        for i in range(len(stages) - 1):
            connect(m, stages[i].o_stream, stages[i + 1].i_stream)
        connect(m, stages[-1].o_stream, wiring.flipped(self.o_stream))

        return m
