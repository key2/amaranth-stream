"""Pipeline components for amaranth-stream.

Provides :class:`Pipeline` (declarative pipeline builder) and
:class:`BufferizeEndpoints` (wrap component with buffers on stream ports).
"""

from amaranth import *
from amaranth.hdl import Signal, ClockDomain
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, connect, FlippedSignature

from ._base import Signature as StreamSignature
from .buffer import Buffer

__all__ = ["Pipeline", "BufferizeEndpoints"]


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


def _unwrap_signature(sig):
    """Unwrap a FlippedSignature to get the original StreamSignature."""
    if isinstance(sig, FlippedSignature):
        return sig.flip()
    return sig


def _connect_streams(m, src, dst, sig):
    """Connect two stream interfaces combinationally.

    src is the output side (drives payload, valid, etc.)
    dst is the input side (drives ready)
    sig is the StreamSignature.
    """
    fwd_names = _get_forward_signals(sig)
    for name in fwd_names:
        m.d.comb += getattr(dst, name).eq(getattr(src, name))
    m.d.comb += [
        dst.valid.eq(src.valid),
        src.ready.eq(dst.ready),
    ]


class Pipeline(wiring.Component):
    """Declarative pipeline builder. Chains stages connecting o_stream → i_stream.

    Parameters
    ----------
    *stages : :class:`wiring.Component`
        Component instances, each with ``i_stream`` and ``o_stream`` ports.

    Ports
    -----
    i_stream : In(first_stage.i_stream.signature)
        Pipeline input, matching the first stage's input signature.
    o_stream : Out(last_stage.o_stream.signature)
        Pipeline output, matching the last stage's output signature.
    """

    def __init__(self, *stages):
        if len(stages) < 1:
            raise ValueError("Pipeline requires at least one stage")
        self._stages = list(stages)

        # Determine signatures from first and last stages
        # We need the original (non-flipped) StreamSignature
        first_sig = self._get_stream_sig(stages[0], "i_stream")
        last_sig = self._get_stream_sig(stages[-1], "o_stream")

        super().__init__({
            "i_stream": In(first_sig),
            "o_stream": Out(last_sig),
        })

    @staticmethod
    def _get_stream_sig(stage, port_name):
        """Extract the StreamSignature from a stage's port.

        Returns the unwrapped (non-flipped) StreamSignature.
        """
        port = getattr(stage, port_name, None)
        if port is None:
            raise ValueError(
                f"Stage {stage!r} does not have a '{port_name}' port")
        sig = _unwrap_signature(port.signature)
        if not isinstance(sig, StreamSignature):
            raise TypeError(
                f"Stage {stage!r}.{port_name} signature is not a "
                f"StreamSignature, got {type(sig).__name__}")
        return sig

    def elaborate(self, platform):
        m = Module()

        # Add all stages as submodules
        for i, stage in enumerate(self._stages):
            m.submodules[f"stage_{i}"] = stage

        first = self._stages[0]
        last = self._stages[-1]

        # Connect pipeline input to first stage
        first_sig = self._get_stream_sig(first, "i_stream")
        _connect_streams(m, wiring.flipped(self.i_stream), first.i_stream, first_sig)

        # Chain intermediate stages
        for i in range(len(self._stages) - 1):
            src_stage = self._stages[i]
            dst_stage = self._stages[i + 1]
            sig = self._get_stream_sig(src_stage, "o_stream")
            _connect_streams(m, src_stage.o_stream, dst_stage.i_stream, sig)

        # Connect last stage to pipeline output
        last_sig = self._get_stream_sig(last, "o_stream")
        _connect_streams(m, last.o_stream, wiring.flipped(self.o_stream), last_sig)

        return m


class BufferizeEndpoints(wiring.Component):
    """Wraps a component, inserting Buffer stages on all stream ports.

    For each ``In`` stream port, a Buffer is inserted before the component.
    For each ``Out`` stream port, a Buffer is inserted after the component.

    Parameters
    ----------
    component : :class:`wiring.Component`
        The component to wrap.
    pipe_valid : :class:`bool`
        If ``True`` (default), register the forward path in buffers.
    pipe_ready : :class:`bool`
        If ``True`` (default), register the backward path in buffers.

    Ports
    -----
    Same as the wrapped component's stream ports.
    """

    def __init__(self, component, *, pipe_valid=True, pipe_ready=True):
        self._component = component
        self._pipe_valid = bool(pipe_valid)
        self._pipe_ready = bool(pipe_ready)

        # Discover stream ports on the wrapped component
        self._in_streams = {}   # name -> StreamSignature
        self._out_streams = {}  # name -> StreamSignature

        for name, member in component.signature.members.items():
            sig = _unwrap_signature(member.signature)
            if isinstance(sig, StreamSignature):
                if member.flow == In:
                    self._in_streams[name] = sig
                elif member.flow == Out:
                    self._out_streams[name] = sig

        # Build our own port signature: same stream ports as the wrapped component
        members = {}
        for name, sig in self._in_streams.items():
            members[name] = In(sig)
        for name, sig in self._out_streams.items():
            members[name] = Out(sig)

        super().__init__(members)

    def elaborate(self, platform):
        m = Module()

        # Add the wrapped component
        m.submodules.core = self._component

        # For each In stream port: add a buffer before the component
        for name, sig in self._in_streams.items():
            buf = Buffer(sig, pipe_valid=self._pipe_valid, pipe_ready=self._pipe_ready)
            m.submodules[f"buf_in_{name}"] = buf

            # Connect: our input -> buffer -> component input
            our_port = getattr(self, name)
            comp_port = getattr(self._component, name)

            # our_port (self.i_stream) is internal view: payload=Out, valid=Out, ready=In
            # flipped: payload=In, valid=In, ready=Out — acts as source
            # buf.i_stream is external view (FlippedInterface): payload=In, valid=In, ready=Out
            # We need source -> sink, so flipped(our_port) drives buf.i_stream
            _connect_streams(m, wiring.flipped(our_port), buf.i_stream, sig)

            # buf.o_stream is external view: payload=Out, valid=Out, ready=In — acts as source
            # comp_port is external view (FlippedInterface): payload=In, valid=In, ready=Out — acts as sink
            _connect_streams(m, buf.o_stream, comp_port, sig)

        # For each Out stream port: add a buffer after the component
        for name, sig in self._out_streams.items():
            buf = Buffer(sig, pipe_valid=self._pipe_valid, pipe_ready=self._pipe_ready)
            m.submodules[f"buf_out_{name}"] = buf

            # comp_port is external view: payload=Out, valid=Out, ready=In — acts as source
            # buf.i_stream is external view (FlippedInterface): payload=In, valid=In, ready=Out — acts as sink
            comp_port = getattr(self._component, name)
            _connect_streams(m, comp_port, buf.i_stream, sig)

            # buf.o_stream is external view: payload=Out, valid=Out, ready=In — acts as source
            # our_port (self.o_stream) is internal view: payload=Out, valid=Out, ready=In
            # flipped: payload=In, valid=In, ready=Out — acts as sink
            our_port = getattr(self, name)
            _connect_streams(m, buf.o_stream, wiring.flipped(our_port), sig)

        return m
