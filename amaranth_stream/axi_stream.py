"""AXI-Stream bridge components for amaranth-stream.

Provides :class:`AXIStreamSignature` for defining AXI-Stream interfaces,
and :class:`AXIStreamToStream` / :class:`StreamToAXIStream` for bridging
between AXI-Stream and amaranth_stream protocols.
"""

from amaranth import *
from amaranth.hdl import Signal, ClockDomain
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ._base import Signature as StreamSignature

__all__ = ["AXIStreamSignature", "AXIStreamToStream", "StreamToAXIStream"]


class AXIStreamSignature(wiring.Signature):
    """AXI-Stream interface definition.

    Parameters
    ----------
    data_width : :class:`int`
        TDATA width in bits. Must be a multiple of 8.
    id_width : :class:`int`
        TID width (0 to omit). Default 0.
    dest_width : :class:`int`
        TDEST width (0 to omit). Default 0.
    user_width : :class:`int`
        TUSER width (0 to omit). Default 0.

    Members
    -------
    tdata : Out(data_width)
    tvalid : Out(1)
    tready : In(1)
    tkeep : Out(data_width // 8)
    tstrb : Out(data_width // 8)
    tlast : Out(1)
    tid : Out(id_width) — if id_width > 0
    tdest : Out(dest_width) — if dest_width > 0
    tuser : Out(user_width) — if user_width > 0
    """

    def __init__(self, data_width, *, id_width=0, dest_width=0, user_width=0):
        if data_width % 8 != 0:
            raise ValueError(
                f"data_width must be a multiple of 8, got {data_width}")
        self._data_width = data_width
        self._id_width = id_width
        self._dest_width = dest_width
        self._user_width = user_width

        members = {
            "tdata": Out(data_width),
            "tvalid": Out(1),
            "tready": In(1),
            "tkeep": Out(data_width // 8),
            "tstrb": Out(data_width // 8),
            "tlast": Out(1),
        }
        if id_width > 0:
            members["tid"] = Out(id_width)
        if dest_width > 0:
            members["tdest"] = Out(dest_width)
        if user_width > 0:
            members["tuser"] = Out(user_width)

        super().__init__(members)

    @property
    def data_width(self):
        return self._data_width

    @property
    def id_width(self):
        return self._id_width

    @property
    def dest_width(self):
        return self._dest_width

    @property
    def user_width(self):
        return self._user_width

    def __eq__(self, other):
        return (isinstance(other, AXIStreamSignature) and
                self._data_width == other._data_width and
                self._id_width == other._id_width and
                self._dest_width == other._dest_width and
                self._user_width == other._user_width)

    def __repr__(self):
        params = [f"{self._data_width}"]
        if self._id_width:
            params.append(f"id_width={self._id_width}")
        if self._dest_width:
            params.append(f"dest_width={self._dest_width}")
        if self._user_width:
            params.append(f"user_width={self._user_width}")
        return f"AXIStreamSignature({', '.join(params)})"


class AXIStreamToStream(wiring.Component):
    """AXI-Stream → amaranth_stream bridge.

    Parameters
    ----------
    axi_signature : :class:`AXIStreamSignature`
        AXI-Stream interface signature.
    stream_signature : :class:`~amaranth_stream.Signature`
        Output stream signature. Must have ``has_first_last=True``
        and ``has_keep=True``.

    Ports
    -----
    axi : In(axi_signature)
        AXI-Stream input.
    o_stream : Out(stream_signature)
        amaranth_stream output.
    """

    def __init__(self, axi_signature, stream_signature):
        if not isinstance(axi_signature, AXIStreamSignature):
            raise TypeError(
                f"Expected AXIStreamSignature, got {type(axi_signature).__name__}")
        if not isinstance(stream_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(stream_signature).__name__}")
        self._axi_sig = axi_signature
        self._stream_sig = stream_signature
        super().__init__({
            "axi": In(axi_signature),
            "o_stream": Out(stream_signature),
        })

    def elaborate(self, platform):
        m = Module()

        # Track first beat: first beat after reset or after last
        is_first = Signal(init=1, name="is_first")

        # Map AXI signals to stream
        m.d.comb += [
            self.o_stream.payload.eq(self.axi.tdata),
            self.o_stream.valid.eq(self.axi.tvalid),
            self.axi.tready.eq(self.o_stream.ready),
        ]

        if self._stream_sig.has_first_last:
            m.d.comb += [
                self.o_stream.first.eq(is_first),
                self.o_stream.last.eq(self.axi.tlast),
            ]

        if self._stream_sig.has_keep:
            m.d.comb += self.o_stream.keep.eq(self.axi.tkeep)

        # Update first tracking on transfer
        transfer = self.axi.tvalid & self.axi.tready
        with m.If(transfer):
            with m.If(self.axi.tlast):
                m.d.sync += is_first.eq(1)
            with m.Else():
                m.d.sync += is_first.eq(0)

        return m


class StreamToAXIStream(wiring.Component):
    """amaranth_stream → AXI-Stream bridge.

    Parameters
    ----------
    stream_signature : :class:`~amaranth_stream.Signature`
        Input stream signature.
    axi_signature : :class:`AXIStreamSignature`
        AXI-Stream output signature.

    Ports
    -----
    i_stream : In(stream_signature)
        amaranth_stream input.
    axi : Out(axi_signature)
        AXI-Stream output.
    """

    def __init__(self, stream_signature, axi_signature):
        if not isinstance(stream_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(stream_signature).__name__}")
        if not isinstance(axi_signature, AXIStreamSignature):
            raise TypeError(
                f"Expected AXIStreamSignature, got {type(axi_signature).__name__}")
        self._stream_sig = stream_signature
        self._axi_sig = axi_signature
        super().__init__({
            "i_stream": In(stream_signature),
            "axi": Out(axi_signature),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        # Map stream signals to AXI
        m.d.comb += [
            self.axi.tdata.eq(self.i_stream.payload),
            self.axi.tvalid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.axi.tready),
        ]

        # Map last → tlast
        if self._stream_sig.has_first_last:
            m.d.comb += self.axi.tlast.eq(self.i_stream.last)

        # Map keep → tkeep, and set tstrb = tkeep
        if self._stream_sig.has_keep:
            m.d.comb += [
                self.axi.tkeep.eq(self.i_stream.keep),
                self.axi.tstrb.eq(self.i_stream.keep),
            ]
        else:
            # Default: all bytes valid
            n_bytes = self._axi_sig.data_width // 8
            m.d.comb += [
                self.axi.tkeep.eq((1 << n_bytes) - 1),
                self.axi.tstrb.eq((1 << n_bytes) - 1),
            ]

        return m
