"""Packet processing components for amaranth-stream.

Provides :class:`HeaderLayout`, :class:`Packetizer`, :class:`Depacketizer`,
:class:`PacketFIFO`, :class:`PacketStatus`, :class:`Stitcher`,
:class:`LastInserter`, and :class:`LastOnTimeout` for packet-level stream
processing.
"""

import math

from amaranth import *
from amaranth.hdl import Shape, Signal, unsigned
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib.data import StructLayout
from amaranth.lib.fifo import SyncFIFO

from ._base import Signature as StreamSignature

__all__ = [
    "HeaderLayout",
    "Packetizer",
    "Depacketizer",
    "PacketFIFO",
    "PacketStatus",
    "Stitcher",
    "LastInserter",
    "LastOnTimeout",
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_forward_signals(sig):
    """Return the list of forward signal names for a stream signature."""
    names = ["payload"]
    if sig.has_first_last:
        names.extend(["first", "last"])
    if sig.param_shape is not None:
        names.append("param")
    if sig.has_keep:
        names.append("keep")
    return names


def _stream_data_width(sig):
    """Calculate the total data width for packing all stream fields into a FIFO word."""
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


# ===========================================================================
# HeaderLayout
# ===========================================================================

class HeaderLayout:
    """Declarative header definition.

    Parameters
    ----------
    fields : :class:`dict`
        Mapping of field name → (width, byte_offset).

    Properties
    ----------
    struct_layout : :class:`StructLayout`
        StructLayout for the header.
    byte_length : :class:`int`
        Total header bytes.
    fields : :class:`dict`
        The original fields dict.
    """

    def __init__(self, fields):
        self._fields = dict(fields)
        # Calculate byte_length from max(byte_offset + ceil(width/8))
        max_end = 0
        for name, (width, byte_offset) in self._fields.items():
            end = byte_offset + math.ceil(width / 8)
            if end > max_end:
                max_end = end
        self._byte_length = max_end

    @property
    def struct_layout(self):
        """Return a StructLayout for the header fields."""
        return StructLayout({name: width for name, (width, _) in self._fields.items()})

    @property
    def byte_length(self):
        """Total header size in bytes."""
        return self._byte_length

    @property
    def fields(self):
        """The original fields dict."""
        return self._fields


# ===========================================================================
# Packetizer
# ===========================================================================

class Packetizer(wiring.Component):
    """Inserts header beats before payload. Latches header on first.

    Parameters
    ----------
    header_layout : :class:`HeaderLayout`
        Header definition.
    payload_signature : :class:`~amaranth_stream.Signature`
        Stream signature (must have has_first_last=True).

    Ports
    -----
    i_stream : In(payload_signature)
        Payload data input.
    o_stream : Out(payload_signature)
        Header + payload data output.
    header : In(header_layout.struct_layout)
        Header fields to insert.
    """

    def __init__(self, header_layout, payload_signature):
        if not isinstance(payload_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(payload_signature).__name__}")
        if not payload_signature.has_first_last:
            raise ValueError("payload_signature must have has_first_last=True")
        self._header_layout = header_layout
        self._payload_sig = payload_signature
        self._payload_width = Shape.cast(payload_signature.payload_shape).width

        # Calculate number of header beats
        header_bits = header_layout.byte_length * 8
        self._header_beats = math.ceil(header_bits / self._payload_width)

        super().__init__({
            "i_stream": In(payload_signature),
            "o_stream": Out(payload_signature),
            "header": In(header_layout.struct_layout),
        })

    def elaborate(self, platform):
        m = Module()

        payload_width = self._payload_width
        header_beats = self._header_beats
        header_layout = self._header_layout

        # Latch the header value
        header_latched = Signal(header_layout.byte_length * 8, name="header_latched")

        # Beat counter for header emission
        beat_cnt = Signal(range(max(header_beats, 1)), name="hdr_beat_cnt")

        with m.FSM(name="packetizer"):
            with m.State("HEADER"):
                # Latch header on entry (first beat)
                with m.If(beat_cnt == 0):
                    # Pack header fields into a flat bit vector
                    offset = 0
                    for name, (width, byte_off) in header_layout.fields.items():
                        m.d.sync += header_latched[byte_off * 8:byte_off * 8 + width].eq(
                            getattr(self.header, name))
                        offset += width

                # Emit header beats from latched value
                # For the first beat, use the header port directly (latched not ready yet)
                with m.If(beat_cnt == 0):
                    # Build header bits directly from input
                    header_flat = Signal(header_layout.byte_length * 8, name="header_flat")
                    offset = 0
                    for name, (width, byte_off) in header_layout.fields.items():
                        m.d.comb += header_flat[byte_off * 8:byte_off * 8 + width].eq(
                            getattr(self.header, name))
                    m.d.comb += self.o_stream.payload.eq(
                        header_flat[0:payload_width])
                with m.Else():
                    # Subsequent beats from latched value
                    start_bit = beat_cnt * payload_width
                    m.d.comb += self.o_stream.payload.eq(
                        header_latched.word_select(beat_cnt, payload_width))

                m.d.comb += [
                    self.o_stream.valid.eq(1),
                    self.o_stream.first.eq(beat_cnt == 0),
                    self.o_stream.last.eq(0),
                    self.i_stream.ready.eq(0),  # Don't consume payload during header
                ]

                # Advance on transfer
                with m.If(self.o_stream.valid & self.o_stream.ready):
                    with m.If(beat_cnt == header_beats - 1):
                        m.d.sync += beat_cnt.eq(0)
                        m.next = "PAYLOAD"
                    with m.Else():
                        m.d.sync += beat_cnt.eq(beat_cnt + 1)

            with m.State("PAYLOAD"):
                # Pass through payload beats
                m.d.comb += [
                    self.o_stream.payload.eq(self.i_stream.payload),
                    self.o_stream.valid.eq(self.i_stream.valid),
                    self.o_stream.first.eq(0),
                    self.o_stream.last.eq(self.i_stream.last),
                    self.i_stream.ready.eq(self.o_stream.ready),
                ]

                # On last beat, go back to HEADER
                with m.If(self.i_stream.valid & self.i_stream.ready & self.i_stream.last):
                    m.next = "HEADER"

        return m


# ===========================================================================
# Depacketizer
# ===========================================================================

class Depacketizer(wiring.Component):
    """Extracts header from packet start. Strips header beats.

    Parameters
    ----------
    header_layout : :class:`HeaderLayout`
        Header definition.
    payload_signature : :class:`~amaranth_stream.Signature`
        Stream signature.

    Ports
    -----
    i_stream : In(payload_signature)
        Header + payload data input.
    o_stream : Out(payload_signature)
        Payload only output.
    header : Out(header_layout.struct_layout)
        Extracted header fields.
    """

    def __init__(self, header_layout, payload_signature):
        if not isinstance(payload_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(payload_signature).__name__}")
        if not payload_signature.has_first_last:
            raise ValueError("payload_signature must have has_first_last=True")
        self._header_layout = header_layout
        self._payload_sig = payload_signature
        self._payload_width = Shape.cast(payload_signature.payload_shape).width

        header_bits = header_layout.byte_length * 8
        self._header_beats = math.ceil(header_bits / self._payload_width)

        super().__init__({
            "i_stream": In(payload_signature),
            "o_stream": Out(payload_signature),
            "header": Out(header_layout.struct_layout),
        })

    def elaborate(self, platform):
        m = Module()

        payload_width = self._payload_width
        header_beats = self._header_beats
        header_layout = self._header_layout

        # Storage for header bits
        header_store = Signal(header_layout.byte_length * 8, name="header_store")

        # Beat counter for header consumption
        beat_cnt = Signal(range(max(header_beats, 1)), name="hdr_beat_cnt")

        # Track if this is the first payload beat after header
        first_payload = Signal(1, name="first_payload")

        with m.FSM(name="depacketizer"):
            with m.State("HEADER"):
                m.d.comb += [
                    self.i_stream.ready.eq(1),  # Consume header beats
                    self.o_stream.valid.eq(0),   # Don't output during header
                ]

                with m.If(self.i_stream.valid & self.i_stream.ready):
                    # Store header beat
                    m.d.sync += header_store.word_select(beat_cnt, payload_width).eq(
                        self.i_stream.payload)

                    with m.If(beat_cnt == header_beats - 1):
                        m.d.sync += [
                            beat_cnt.eq(0),
                            first_payload.eq(1),
                        ]
                        m.next = "PAYLOAD"
                    with m.Else():
                        m.d.sync += beat_cnt.eq(beat_cnt + 1)

            with m.State("PAYLOAD"):
                # Pass through payload beats
                m.d.comb += [
                    self.o_stream.payload.eq(self.i_stream.payload),
                    self.o_stream.valid.eq(self.i_stream.valid),
                    self.o_stream.first.eq(first_payload),
                    self.o_stream.last.eq(self.i_stream.last),
                    self.i_stream.ready.eq(self.o_stream.ready),
                ]

                with m.If(self.i_stream.valid & self.i_stream.ready):
                    m.d.sync += first_payload.eq(0)

                    with m.If(self.i_stream.last):
                        m.next = "HEADER"

        # Extract header fields from stored bits
        for name, (width, byte_off) in header_layout.fields.items():
            m.d.comb += getattr(self.header, name).eq(
                header_store[byte_off * 8:byte_off * 8 + width])

        return m


# ===========================================================================
# PacketFIFO
# ===========================================================================

class PacketFIFO(wiring.Component):
    """Atomic packet FIFO. Only releases complete packets.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (must have has_first_last=True).
    payload_depth : :class:`int`
        Max payload beats.
    packet_depth : :class:`int`
        Max buffered packets (default 16).

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream.
    packet_count : Out(range(packet_depth + 1))
        Number of complete packets available.
    """

    def __init__(self, signature, payload_depth, packet_depth=16):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not signature.has_first_last:
            raise ValueError("signature must have has_first_last=True")
        self._stream_sig = signature
        self._payload_depth = payload_depth
        self._packet_depth = packet_depth

        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
            "packet_count": Out(range(packet_depth + 1)),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig
        total_width, fields = _stream_data_width(sig)

        # Data FIFO: stores packed stream data
        data_fifo = SyncFIFO(width=total_width, depth=self._payload_depth)
        m.submodules.data_fifo = data_fifo

        # Packet length FIFO: stores beat counts for complete packets
        len_width = max(1, (self._payload_depth).bit_length())
        pkt_fifo = SyncFIFO(width=len_width, depth=self._packet_depth)
        m.submodules.pkt_fifo = pkt_fifo

        # --- Write side ---
        # Pack stream fields into data word
        pack_signals = []
        for name, _width in fields:
            pack_signals.append(getattr(self.i_stream, name))

        # Beat counter for current packet being written
        wr_beat_cnt = Signal(range(self._payload_depth + 1), name="wr_beat_cnt")

        # Write to data FIFO
        w_transfer = Signal(name="w_transfer")
        m.d.comb += [
            data_fifo.w_data.eq(Cat(*pack_signals)),
            w_transfer.eq(self.i_stream.valid & self.i_stream.ready),
            data_fifo.w_en.eq(w_transfer),
        ]

        # Accept input when data FIFO has space
        m.d.comb += self.i_stream.ready.eq(data_fifo.w_rdy)

        # Track beats and commit packets
        with m.If(w_transfer):
            m.d.sync += wr_beat_cnt.eq(wr_beat_cnt + 1)
            with m.If(self.i_stream.last):
                # Commit: write beat count to packet FIFO
                m.d.comb += [
                    pkt_fifo.w_data.eq(wr_beat_cnt + 1),
                    pkt_fifo.w_en.eq(1),
                ]
                m.d.sync += wr_beat_cnt.eq(0)

        # --- Read side ---
        # Read beat counter for current packet being read
        rd_beat_cnt = Signal(range(self._payload_depth + 1), name="rd_beat_cnt")
        rd_pkt_len = Signal(len_width, name="rd_pkt_len")
        reading = Signal(name="reading")

        # Unpack data FIFO output
        offset = 0
        for name, width in fields:
            m.d.comb += getattr(self.o_stream, name).eq(data_fifo.r_data[offset:offset + width])
            offset += width

        # Output valid only when we have a packet to read
        m.d.comb += self.o_stream.valid.eq(reading & data_fifo.r_rdy)

        # Override first/last from the FIFO data with our own framing
        m.d.comb += [
            self.o_stream.first.eq(reading & (rd_beat_cnt == 0)),
            self.o_stream.last.eq(reading & (rd_beat_cnt == rd_pkt_len - 1)),
        ]

        r_transfer = Signal(name="r_transfer")
        m.d.comb += [
            r_transfer.eq(self.o_stream.valid & self.o_stream.ready),
            data_fifo.r_en.eq(r_transfer),
        ]

        with m.If(~reading):
            # Not currently reading a packet — check if one is available
            with m.If(pkt_fifo.r_rdy):
                m.d.sync += [
                    rd_pkt_len.eq(pkt_fifo.r_data),
                    rd_beat_cnt.eq(0),
                    reading.eq(1),
                ]
                m.d.comb += pkt_fifo.r_en.eq(1)
        with m.Else():
            # Currently reading a packet
            with m.If(r_transfer):
                with m.If(rd_beat_cnt == rd_pkt_len - 1):
                    # Finished this packet
                    m.d.sync += reading.eq(0)
                with m.Else():
                    m.d.sync += rd_beat_cnt.eq(rd_beat_cnt + 1)

        # Packet count
        m.d.comb += self.packet_count.eq(pkt_fifo.level)

        return m


# ===========================================================================
# PacketStatus
# ===========================================================================

class PacketStatus(wiring.Component):
    """Packet boundary tracker. Tap-only (non-consuming).

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature.

    Ports
    -----
    stream : In(signature)
        Tap-only stream (does NOT drive ready).
    in_packet : Out(1)
        High when inside a packet.
    """

    def __init__(self, signature):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not signature.has_first_last:
            raise ValueError("signature must have has_first_last=True")
        self._stream_sig = signature
        super().__init__({
            "stream": In(signature),
            "in_packet": Out(1),
        })

    def elaborate(self, platform):
        m = Module()

        transfer = Signal(name="transfer")
        m.d.comb += transfer.eq(self.stream.valid & self.stream.ready)

        in_pkt = Signal(name="in_pkt")

        with m.If(transfer & self.stream.first):
            m.d.sync += in_pkt.eq(1)
        with m.If(transfer & self.stream.last):
            m.d.sync += in_pkt.eq(0)

        m.d.comb += self.in_packet.eq(in_pkt)

        # NOTE: We do NOT drive self.stream.ready — this is a passive tap.

        return m


# ===========================================================================
# Stitcher
# ===========================================================================

class Stitcher(wiring.Component):
    """Groups N consecutive packets into one by suppressing intermediate first/last.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (must have has_first_last=True).
    n : :class:`int`
        Number of packets to stitch.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream with stitched packets.
    """

    def __init__(self, signature, n):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not signature.has_first_last:
            raise ValueError("signature must have has_first_last=True")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        self._stream_sig = signature
        self._n = n
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig
        n = self._n

        # Packet counter (0 to n-1)
        pkt_cnt = Signal(range(n), name="pkt_cnt")

        # Pass through payload and handshake
        m.d.comb += [
            self.o_stream.payload.eq(self.i_stream.payload),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Pass through optional signals
        if sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)
        if sig.has_keep:
            m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)

        # First: only on the first beat of the first packet
        m.d.comb += self.o_stream.first.eq(
            self.i_stream.first & (pkt_cnt == 0))

        # Last: only on the last beat of the Nth packet
        m.d.comb += self.o_stream.last.eq(
            self.i_stream.last & (pkt_cnt == n - 1))

        # Count packets on last beat transfer
        transfer = Signal(name="transfer")
        m.d.comb += transfer.eq(self.i_stream.valid & self.i_stream.ready)

        with m.If(transfer & self.i_stream.last):
            with m.If(pkt_cnt == n - 1):
                m.d.sync += pkt_cnt.eq(0)
            with m.Else():
                m.d.sync += pkt_cnt.eq(pkt_cnt + 1)

        return m


# ===========================================================================
# LastInserter
# ===========================================================================

class LastInserter(wiring.Component):
    """Injects last=1 every N beats (fixed-size packet creation).

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (must have has_first_last=True).
    n : :class:`int`
        Packet length in beats.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream with injected first/last.
    """

    def __init__(self, signature, n):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not signature.has_first_last:
            raise ValueError("signature must have has_first_last=True")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        self._stream_sig = signature
        self._n = n
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig
        n = self._n

        # Beat counter (0 to n-1)
        beat_cnt = Signal(range(n), name="beat_cnt")

        # Pass through payload and handshake
        m.d.comb += [
            self.o_stream.payload.eq(self.i_stream.payload),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Pass through optional signals
        if sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)
        if sig.has_keep:
            m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)

        # first on beat 0, last on beat n-1
        m.d.comb += [
            self.o_stream.first.eq(beat_cnt == 0),
            self.o_stream.last.eq(beat_cnt == n - 1),
        ]

        # Count beats on transfer
        transfer = Signal(name="transfer")
        m.d.comb += transfer.eq(self.i_stream.valid & self.i_stream.ready)

        with m.If(transfer):
            with m.If(beat_cnt == n - 1):
                m.d.sync += beat_cnt.eq(0)
            with m.Else():
                m.d.sync += beat_cnt.eq(beat_cnt + 1)

        return m


# ===========================================================================
# LastOnTimeout
# ===========================================================================

class LastOnTimeout(wiring.Component):
    """Injects last=1 after configurable idle timeout.

    Parameters
    ----------
    signature : :class:`~amaranth_stream.Signature`
        Stream signature (must have has_first_last=True).
    timeout : :class:`int`
        Idle cycles before injecting last.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream with timeout-injected last.
    """

    def __init__(self, signature, timeout):
        if not isinstance(signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature, got {type(signature).__name__}")
        if not signature.has_first_last:
            raise ValueError("signature must have has_first_last=True")
        if timeout < 1:
            raise ValueError(f"timeout must be >= 1, got {timeout}")
        self._stream_sig = signature
        self._timeout = timeout
        super().__init__({
            "i_stream": In(signature),
            "o_stream": Out(signature),
        })

    def elaborate(self, platform):
        m = Module()

        sig = self._stream_sig
        timeout = self._timeout

        # Idle counter
        idle_cnt = Signal(range(timeout + 1), name="idle_cnt")
        # Whether we're inside a packet (seen first, not yet seen last)
        in_packet = Signal(name="in_packet")
        # Force last on next transfer
        force_last = Signal(name="force_last")

        # Pass through payload and handshake
        m.d.comb += [
            self.o_stream.payload.eq(self.i_stream.payload),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Pass through optional signals
        if sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)
        if sig.has_keep:
            m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)

        # first passes through
        m.d.comb += self.o_stream.first.eq(self.i_stream.first)

        # last: pass through OR force
        m.d.comb += self.o_stream.last.eq(self.i_stream.last | force_last)

        transfer = Signal(name="transfer")
        m.d.comb += transfer.eq(self.i_stream.valid & self.i_stream.ready)

        # Track packet state and idle counter
        with m.If(transfer):
            m.d.sync += idle_cnt.eq(0)
            with m.If(self.i_stream.first):
                m.d.sync += in_packet.eq(1)
            with m.If(self.i_stream.last | force_last):
                m.d.sync += [
                    in_packet.eq(0),
                    force_last.eq(0),
                ]
        with m.Elif(in_packet):
            # No transfer this cycle, increment idle counter
            with m.If(idle_cnt < timeout):
                m.d.sync += idle_cnt.eq(idle_cnt + 1)
            with m.If(idle_cnt == timeout - 1):
                m.d.sync += force_last.eq(1)

        return m
