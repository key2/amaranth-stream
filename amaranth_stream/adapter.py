"""SOP/EOP protocol adapter components for amaranth-stream.

Provides :class:`SOPEOPAdapter` and :class:`StreamToSOPEOP` for bridging
between SOP/EOP/valid-mask framing (common in FPGA hard IP such as Gowin PCIe,
Xilinx Aurora, Intel Avalon-ST) and amaranth-stream's valid/ready/first/last
framing.
"""

import math

from amaranth import *
from amaranth.hdl import Signal, Shape, Cat, ClockDomain
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ._base import Signature as StreamSignature

__all__ = ["SOPEOPAdapter", "StreamToSOPEOP"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_mask_width(data_width, granularity):
    """Return the width of the valid-mask signal for the given granularity."""
    if granularity == "bit":
        return data_width
    elif granularity == "byte":
        return data_width // 8
    elif granularity == "dword":
        return data_width // 32
    else:
        raise ValueError(
            f"granularity must be 'bit', 'byte', or 'dword', got {granularity!r}")


def _keep_width(data_width):
    """Return the byte-enable (keep) width for the given data width."""
    return data_width // 8


def _expand_valid_mask_to_keep(m, valid_mask, data_width, granularity):
    """Create combinational logic to expand a valid-mask to byte-level keep.

    Returns a Signal of width ``data_width // 8``.
    """
    keep_w = _keep_width(data_width)
    keep = Signal(keep_w, name="keep_expanded")

    if granularity == "byte":
        # 1:1 mapping — each mask bit corresponds to one byte
        m.d.comb += keep.eq(valid_mask)
    elif granularity == "bit":
        # Each group of 8 mask bits → 1 keep bit (OR-reduce each group)
        parts = []
        for i in range(keep_w):
            group = valid_mask[i * 8:(i + 1) * 8]
            parts.append(group.any())
        m.d.comb += keep.eq(Cat(*parts))
    elif granularity == "dword":
        # Each mask bit → 4 keep bits (one DWORD = 4 bytes)
        dword_count = data_width // 32
        parts = []
        for i in range(dword_count):
            # Replicate each mask bit 4 times
            for _ in range(4):
                parts.append(valid_mask[i])
        m.d.comb += keep.eq(Cat(*parts))

    return keep


def _compress_keep_to_valid_mask(m, keep, data_width, granularity):
    """Create combinational logic to compress byte-level keep to a valid-mask.

    Returns a Signal of width matching the granularity.
    """
    mask_w = _valid_mask_width(data_width, granularity)
    valid_mask = Signal(mask_w, name="valid_mask_compressed")

    if granularity == "byte":
        # 1:1 mapping
        m.d.comb += valid_mask.eq(keep)
    elif granularity == "bit":
        # Each keep bit → 8 mask bits (replicate)
        keep_w = _keep_width(data_width)
        parts = []
        for i in range(keep_w):
            for _ in range(8):
                parts.append(keep[i])
        m.d.comb += valid_mask.eq(Cat(*parts))
    elif granularity == "dword":
        # Each group of 4 keep bits → 1 mask bit (AND-reduce)
        dword_count = data_width // 32
        parts = []
        for i in range(dword_count):
            group = keep[i * 4:(i + 1) * 4]
            parts.append(group.all())
        m.d.comb += valid_mask.eq(Cat(*parts))

    return valid_mask


def _reorder_dwords(data_signal, data_width):
    """Return a Cat expression with DWORDs in reversed order."""
    n_dwords = data_width // 32
    dwords = []
    for i in range(n_dwords):
        dwords.append(data_signal[i * 32:(i + 1) * 32])
    dwords.reverse()
    return Cat(*dwords)


# ---------------------------------------------------------------------------
# SOP/EOP Signature (for the hard-IP side)
# ---------------------------------------------------------------------------

class SOPEOPSignature(wiring.Signature):
    """SOP/EOP interface signature for FPGA hard IP.

    Parameters
    ----------
    data_width : :class:`int`
        Data bus width in bits.
    granularity : :class:`str`
        Valid-mask granularity: ``"bit"``, ``"byte"``, or ``"dword"``.
    """

    def __init__(self, data_width, granularity="byte"):
        self._data_width = data_width
        self._granularity = granularity
        mask_w = _valid_mask_width(data_width, granularity)

        members = {
            "data":       Out(data_width),
            "sop":        Out(1),
            "eop":        Out(1),
            "valid_mask": Out(mask_w),
            "valid":      Out(1),
            "ready":      In(1),
        }
        super().__init__(members)

    @property
    def data_width(self):
        return self._data_width

    @property
    def granularity(self):
        return self._granularity


# ---------------------------------------------------------------------------
# SOPEOPAdapter: SOP/EOP → amaranth-stream
# ---------------------------------------------------------------------------

class SOPEOPAdapter(wiring.Component):
    """Convert SOP/EOP/valid-mask framing to amaranth-stream.

    Bridges from FPGA hard IP interfaces (Gowin PCIe, Xilinx Aurora,
    Intel Avalon-ST style) to amaranth-stream's valid/ready/first/last
    protocol.

    Parameters
    ----------
    data_width : :class:`int`
        Width of the data bus in bits (e.g. 256). Must be a multiple of 32.
    granularity : :class:`str`
        Valid-mask granularity: ``"bit"``, ``"byte"`` (default), or ``"dword"``.
    dword_reorder : :class:`bool`
        When ``True``, reverses DWORD order within the data word.

    Ports
    -----
    sink : In(SOPEOPSignature)
        SOP/EOP input from hard IP.
    source : Out(StreamSignature)
        amaranth-stream output with ``first``, ``last``, and ``keep``.
    """

    def __init__(self, data_width, *, granularity="byte", dword_reorder=False):
        if data_width % 32 != 0:
            raise ValueError(
                f"data_width must be a multiple of 32, got {data_width}")
        if granularity not in ("bit", "byte", "dword"):
            raise ValueError(
                f"granularity must be 'bit', 'byte', or 'dword', got {granularity!r}")

        self._data_width = data_width
        self._granularity = granularity
        self._dword_reorder = dword_reorder

        sop_eop_sig = SOPEOPSignature(data_width, granularity)
        stream_sig = StreamSignature(
            data_width, has_first_last=True, has_keep=True)

        super().__init__({
            "sink":   In(sop_eop_sig),
            "source": Out(stream_sig),
        })

    @property
    def data_width(self):
        return self._data_width

    @property
    def granularity(self):
        return self._granularity

    @property
    def dword_reorder(self):
        return self._dword_reorder

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        # --- Data path ---
        if self._dword_reorder:
            reordered = _reorder_dwords(self.sink.data, self._data_width)
            m.d.comb += self.source.payload.eq(reordered)
        else:
            m.d.comb += self.source.payload.eq(self.sink.data)

        # --- Framing ---
        m.d.comb += [
            self.source.first.eq(self.sink.sop),
            self.source.last.eq(self.sink.eop),
        ]

        # --- Valid-mask → keep expansion ---
        keep = _expand_valid_mask_to_keep(
            m, self.sink.valid_mask, self._data_width, self._granularity)
        m.d.comb += self.source.keep.eq(keep)

        # --- Handshake ---
        m.d.comb += [
            self.source.valid.eq(self.sink.valid),
            self.sink.ready.eq(self.source.ready),
        ]

        return m


# ---------------------------------------------------------------------------
# StreamToSOPEOP: amaranth-stream → SOP/EOP
# ---------------------------------------------------------------------------

class StreamToSOPEOP(wiring.Component):
    """Convert amaranth-stream to SOP/EOP/valid-mask framing.

    Bridges from amaranth-stream's valid/ready/first/last protocol to
    FPGA hard IP interfaces.

    Parameters
    ----------
    data_width : :class:`int`
        Width of the data bus in bits (e.g. 256). Must be a multiple of 32.
    granularity : :class:`str`
        Valid-mask granularity: ``"bit"``, ``"byte"`` (default), or ``"dword"``.
    dword_reorder : :class:`bool`
        When ``True``, reverses DWORD order within the data word.

    Ports
    -----
    sink : In(StreamSignature)
        amaranth-stream input with ``first``, ``last``, and ``keep``.
    source : Out(SOPEOPSignature)
        SOP/EOP output to hard IP.
    """

    def __init__(self, data_width, *, granularity="byte", dword_reorder=False):
        if data_width % 32 != 0:
            raise ValueError(
                f"data_width must be a multiple of 32, got {data_width}")
        if granularity not in ("bit", "byte", "dword"):
            raise ValueError(
                f"granularity must be 'bit', 'byte', or 'dword', got {granularity!r}")

        self._data_width = data_width
        self._granularity = granularity
        self._dword_reorder = dword_reorder

        stream_sig = StreamSignature(
            data_width, has_first_last=True, has_keep=True)
        sop_eop_sig = SOPEOPSignature(data_width, granularity)

        super().__init__({
            "sink":   In(stream_sig),
            "source": Out(sop_eop_sig),
        })

    @property
    def data_width(self):
        return self._data_width

    @property
    def granularity(self):
        return self._granularity

    @property
    def dword_reorder(self):
        return self._dword_reorder

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        # --- Data path ---
        if self._dword_reorder:
            reordered = _reorder_dwords(self.sink.payload, self._data_width)
            m.d.comb += self.source.data.eq(reordered)
        else:
            m.d.comb += self.source.data.eq(self.sink.payload)

        # --- Framing ---
        m.d.comb += [
            self.source.sop.eq(self.sink.first),
            self.source.eop.eq(self.sink.last),
        ]

        # --- Keep → valid-mask compression ---
        valid_mask = _compress_keep_to_valid_mask(
            m, self.sink.keep, self._data_width, self._granularity)
        m.d.comb += self.source.valid_mask.eq(valid_mask)

        # --- Handshake ---
        m.d.comb += [
            self.source.valid.eq(self.sink.valid),
            self.sink.ready.eq(self.source.ready),
        ]

        return m
