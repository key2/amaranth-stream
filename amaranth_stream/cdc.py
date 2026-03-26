"""Clock-domain crossing component for amaranth-stream.

Provides :class:`StreamCDC` which automatically selects between a simple
:class:`PipeValid` (same domain) and a :class:`StreamAsyncFIFO` (different
domains).
"""

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, connect

from ._base import Signature as StreamSignature
from .buffer import PipeValid
from .fifo import StreamAsyncFIFO

__all__ = ["StreamCDC"]


class StreamCDC(wiring.Component):
    """Automatic clock-domain crossing for streams.

    When ``w_domain == r_domain``, instantiates a :class:`PipeValid`
    (forward-registered pipeline stage, 1-cycle latency). When the domains
    differ, instantiates a :class:`StreamAsyncFIFO` for safe cross-domain
    transfer.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature for both input and output ports.
    depth : :class:`int`
        FIFO depth for the cross-domain case (default 8).
    w_domain : :class:`str`
        Write clock domain (default ``"sync"``).
    r_domain : :class:`str`
        Read clock domain (default ``"sync"``).

    Ports
    -----
    i_stream : In(signature)
        Input stream (in ``w_domain``).
    o_stream : Out(signature)
        Output stream (in ``r_domain``).
    """

    def __init__(self, signature, *, depth=8, w_domain="sync", r_domain="sync"):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        self._stream_sig = signature
        self._depth = depth
        self._w_domain = w_domain
        self._r_domain = r_domain
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()

        if self._w_domain == self._r_domain:
            # Same domain: use PipeValid (1-cycle latency)
            pv = PipeValid(self._stream_sig)
            m.submodules.pv = pv
            connect(m, wiring.flipped(self.i_stream), pv.i_stream)
            connect(m, pv.o_stream, wiring.flipped(self.o_stream))
        else:
            # Different domains: use StreamAsyncFIFO
            fifo = StreamAsyncFIFO(
                self._stream_sig, self._depth,
                w_domain=self._w_domain, r_domain=self._r_domain)
            m.submodules.fifo = fifo
            connect(m, wiring.flipped(self.i_stream), fifo.i_stream)
            connect(m, fifo.o_stream, wiring.flipped(self.o_stream))

        return m
