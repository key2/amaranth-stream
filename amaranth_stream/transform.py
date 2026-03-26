"""Data transformation components for amaranth-stream.

Provides :class:`StreamMap`, :class:`StreamFilter`, :class:`EndianSwap`,
:class:`GranularEndianSwap`, :class:`ByteAligner`, :class:`PacketAligner`,
and :class:`WordReorder` for transforming stream payloads.
"""

import math

from amaranth import *
from amaranth.hdl import Signal, Shape, Cat, Mux, ClockDomain
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from ._base import Signature as StreamSignature

__all__ = ["StreamMap", "StreamFilter", "EndianSwap", "GranularEndianSwap", "ByteAligner",
           "PacketAligner", "WordReorder"]


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


class GranularEndianSwap(wiring.Component):
    """Per-chunk byte-order reversal for multi-DWORD streams.

    Unlike :class:`EndianSwap` which reverses all bytes across the full data
    width, this component reverses bytes independently within each
    ``chunk_size``-bit chunk.  This is required by PCIe and many protocols
    that need per-DWORD (32-bit) independent byte reversal.

    Parameters
    ----------
    data_width : :class:`int`
        Total data width in bits.  Must be a multiple of *chunk_size*.
    chunk_size : :class:`int`
        Size of each chunk in bits (default 32 for DWORD).  Must be a
        multiple of 8.
    field : :class:`str`
        Which payload field to swap (default ``"dat"``).  Currently only
        ``"dat"`` (the payload) is supported.
    be_mode : :class:`bool`
        When ``True``, also reverse the byte-enable (``keep``) bits within
        each chunk.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream with per-chunk reversed byte order.
    """

    def __init__(self, data_width, chunk_size=32, *, field="dat", be_mode=False):
        if chunk_size % 8 != 0:
            raise ValueError(
                f"chunk_size must be a multiple of 8, got {chunk_size}")
        if data_width % chunk_size != 0:
            raise ValueError(
                f"data_width ({data_width}) must be a multiple of "
                f"chunk_size ({chunk_size})")
        self._data_width = data_width
        self._chunk_size = chunk_size
        self._field = field
        self._be_mode = be_mode

        sig_kwargs = dict(has_first_last=True, has_keep=be_mode)
        sig = StreamSignature(unsigned(data_width), **sig_kwargs)
        self._stream_sig = sig
        super().__init__({
            "i_stream": In(sig),
            "o_stream": Out(sig),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        n_chunks = self._data_width // self._chunk_size
        bytes_per_chunk = self._chunk_size // 8

        # Reverse bytes within each chunk independently
        reversed_chunks = []
        for c in range(n_chunks):
            chunk_bytes = []
            for b in range(bytes_per_chunk):
                bit_lo = c * self._chunk_size + b * 8
                bit_hi = bit_lo + 8
                chunk_bytes.append(self.i_stream.payload[bit_lo:bit_hi])
            chunk_bytes.reverse()
            reversed_chunks.extend(chunk_bytes)

        m.d.comb += [
            self.o_stream.payload.eq(Cat(*reversed_chunks)),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Pass through first/last
        if self._stream_sig.has_first_last:
            m.d.comb += [
                self.o_stream.first.eq(self.i_stream.first),
                self.o_stream.last.eq(self.i_stream.last),
            ]

        # Handle keep (byte-enable) bits
        if self._stream_sig.has_keep:
            if self._be_mode:
                # Reverse keep bits within each chunk
                reversed_keep = []
                for c in range(n_chunks):
                    keep_bits = []
                    for b in range(bytes_per_chunk):
                        keep_bits.append(
                            self.i_stream.keep[c * bytes_per_chunk + b])
                    keep_bits.reverse()
                    reversed_keep.extend(keep_bits)
                m.d.comb += self.o_stream.keep.eq(Cat(*reversed_keep))
            else:
                m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)

        if self._stream_sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)

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


class PacketAligner(wiring.Component):
    """Cross-beat packet realignment for wide data buses.

    Many protocols (e.g. PCIe PHY RX) deliver packets that start at a
    non-zero offset within a wide data word.  This component stitches data
    across beat boundaries so that the output packet is aligned to offset 0.

    Parameters
    ----------
    data_width : :class:`int`
        Total data width in bits (e.g. 128).
    granularity : :class:`int`
        Alignment granularity in bits (default 32 for DWORD alignment).
        ``data_width`` must be a multiple of ``granularity``.

    Ports
    -----
    i_stream : In(signature)
        Input stream with ``has_first_last=True``.
    o_stream : Out(signature)
        Output stream with realigned payload.
    offset : In(range(n_lanes))
        Starting offset in granularity units for the current packet.
        Sampled when ``first=1`` on the input.
    """

    def __init__(self, data_width, granularity=32):
        if data_width % granularity != 0:
            raise ValueError(
                f"data_width ({data_width}) must be a multiple of "
                f"granularity ({granularity})")
        if data_width < granularity:
            raise ValueError(
                f"data_width ({data_width}) must be >= granularity ({granularity})")

        self._data_width = data_width
        self._granularity = granularity
        self._n_lanes = data_width // granularity

        sig = StreamSignature(unsigned(data_width), has_first_last=True)
        self._stream_sig = sig
        super().__init__({
            "i_stream": In(sig),
            "o_stream": Out(sig),
            "offset": In(range(self._n_lanes)),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        dw = self._data_width
        gran = self._granularity
        n_lanes = self._n_lanes

        # Registered offset, sampled on first beat
        r_offset = Signal(range(n_lanes), name="r_offset")
        # Carry register: stores the upper portion of the previous beat
        carry = Signal(dw, name="carry")
        # Track whether we need to emit a flush beat
        r_first_out = Signal(name="r_first_out")
        r_last_seen = Signal(name="r_last_seen")

        # Shift amount in bits = r_offset * granularity
        shift_bits = Signal(range(dw + 1), name="shift_bits")
        m.d.comb += shift_bits.eq(r_offset * gran)

        # Assembled output: carry (lower portion) | input upper portion
        # output = (input << (dw - shift_bits)) | carry  -- but we use Cat approach
        # Actually: output = carry_bits | (input_lower << carry_width)
        # More precisely:
        #   carry holds the upper (dw - shift_bits) bits of the previous beat
        #   We take the lower shift_bits of the current beat
        #   output = Cat(carry[:dw - shift_bits], current[:shift_bits])
        # But since shift_bits is dynamic, we use a wide shift approach:
        #
        # combined = Cat(carry, input) -- 2*dw bits wide
        # output = (combined >> (dw - shift_bits))[:dw]  -- but this is complex
        #
        # Simpler: use barrel shifter on concatenation
        # When offset=N, shift_bits = N*gran
        # carry stores input[shift_bits:] from previous beat (the upper dw-shift_bits bits)
        # output = (carry << shift_bits) | input[:shift_bits]
        # But carry is only dw-shift_bits wide, so:
        # output = Cat(carry[:dw - shift_bits], input[:shift_bits])
        #
        # Since shift_bits is dynamic, let's use: output = (input << (dw - shift_bits)) | carry
        # No -- let's just do it with a wide concatenation and shift:
        #
        # combined[2*dw-1:0] = Cat(carry, i_stream.payload)
        # output = combined[dw - shift_bits : 2*dw - shift_bits]
        # Which equals: (combined >> (dw - shift_bits))[:dw]
        #
        # Actually the simplest correct approach:
        # carry holds the UPPER bits of previous beat that weren't output yet
        # Specifically, carry = prev_input[shift_bits:dw] (the top dw-shift_bits bits)
        # These go into the LOWER part of the output.
        # The UPPER part comes from current_input[0:shift_bits]
        # output = Cat(carry[0:dw-shift_bits], current_input[0:shift_bits])
        #
        # With dynamic shift, use: combined = Cat(carry, current_input)
        # output = combined >> 0, but we need to select the right window.
        # Let's use: output = (current_input << (dw - shift_bits)) | (carry >> 0)
        # Hmm, carry is dw bits wide (padded), only lower dw-shift_bits are valid.
        #
        # Let me think differently with a mux-based barrel shifter:
        # combined = Cat(carry, i_stream.payload)  -- 2*dw bits
        # We want bits [(dw - shift_bits) : (2*dw - shift_bits)]
        # = combined >> (dw - shift_bits), take lower dw bits
        # But (dw - shift_bits) = dw - r_offset*gran
        # When offset=0: we want combined[dw:2*dw] = i_stream.payload (pass-through) ✓
        # When offset=2 (128-bit, 32-gran): shift_bits=64, want combined[64:192]
        #   = carry[64:128] | input[0:64] ... but carry is 128 bits, carry[64:128] is upper half
        #   Actually carry stores prev[64:128] in carry[0:64], so combined[64:192] =
        #   carry[64:127]|input[0:63] -- that's wrong.
        #
        # Let me reconsider. Let's define:
        # carry = previous_beat[shift_bits : dw]  (stored in carry[0 : dw-shift_bits])
        # We want output = Cat(carry[0:dw-shift_bits], current[0:shift_bits])
        #
        # Using combined = Cat(carry, current_input):
        # combined[0 : dw-shift_bits] = carry[0 : dw-shift_bits]  ✓
        # combined[dw : dw+shift_bits] = current[0 : shift_bits]  ✓
        # But we need them contiguous. The gap is combined[dw-shift_bits : dw] which is
        # carry[dw-shift_bits : dw] (garbage/zero).
        #
        # Better approach: just use a right-shift on a different concatenation.
        # Let assembled = Cat(previous_upper_bits, current_beat)
        # where previous_upper_bits are right-justified in a dw-wide register.
        #
        # Simplest correct approach with dynamic offset:
        # Store carry as the full previous beat (or relevant portion).
        # assembled = Cat(carry, i_stream.payload)  -- 2*dw bits
        # output = (assembled >> shift_bits)[:dw]
        # Where carry = previous full beat.
        # When offset=2, shift_bits=64:
        #   assembled = Cat(prev, curr) = prev[0:127] | curr[0:127] << 128
        #   assembled >> 64 = prev[64:127] | curr[0:63] << 64 | curr[64:127] << 128
        #   lower dw bits = prev[64:127] | curr[0:63] << 64  ✓✓✓
        # When offset=0, shift_bits=0:
        #   assembled >> 0 = Cat(prev, curr), lower dw = prev  -- WRONG, we want curr!
        #
        # Fix: swap order. assembled = Cat(i_stream.payload, carry) -- no.
        # Or: when offset=0, just pass through (special case in FSM).
        # Or: use assembled = Cat(carry, i_stream.payload) and shift by (dw - shift_bits)?
        # assembled >> (dw - shift_bits), lower dw bits:
        # offset=0: >> dw, lower dw = i_stream.payload ✓
        # offset=2 (shift=64): >> 64, lower dw = carry[64:127]|curr[0:63]<<64 ✓
        # Wait that's the same issue. Let me just be precise:
        #
        # assembled[2*dw-1:0] = {i_stream.payload, carry} (Verilog notation, MSB first)
        # In Amaranth Cat: Cat(carry, i_stream.payload)
        #   bit 0..dw-1 = carry
        #   bit dw..2*dw-1 = i_stream.payload
        # (assembled >> shift_bits)[dw-1:0]:
        #   offset=2, shift=64: bits [64..191] = carry[64..127], input[0..63] ✓
        #   offset=0, shift=0: bits [0..127] = carry[0..127] ✗ (want input)
        #
        # So for offset=0 this doesn't work. But offset=0 is pass-through anyway.
        # For offset!=0, on the first beat we just store carry and don't output.
        # On subsequent beats, output = (Cat(carry, input) >> shift_bits)[:dw].
        # carry is updated to the full current input beat each cycle.
        # This works! Let me verify:
        #   Beat 0 (first): carry = beat0, no output
        #   Beat 1: output = (Cat(beat0, beat1) >> shift_bits)[:dw]
        #           = beat0[shift_bits:dw] | beat1[0:shift_bits] << (dw-shift_bits) ✓
        #           carry = beat1
        #   Beat 2 (last): output = (Cat(beat1, beat2) >> shift_bits)[:dw] ✓
        #           carry = beat2
        #   Flush: output = (Cat(beat2, 0) >> shift_bits)[:dw]
        #          = beat2[shift_bits:dw] | 0  ✓ (remaining data from last beat)

        combined = Signal(2 * dw, name="combined")
        aligned_data = Signal(dw, name="aligned_data")

        m.d.comb += [
            combined.eq(Cat(carry, self.i_stream.payload)),
            aligned_data.eq((combined >> shift_bits)[:dw]),
        ]

        # Flush data: carry shifted right by shift_bits (no new input)
        flush_combined = Signal(2 * dw, name="flush_combined")
        flush_data = Signal(dw, name="flush_data")
        m.d.comb += [
            flush_combined.eq(Cat(carry, 0)),
            flush_data.eq((flush_combined >> shift_bits)[:dw]),
        ]

        # Default: output not valid, input not ready
        m.d.comb += [
            self.o_stream.valid.eq(0),
            self.o_stream.payload.eq(0),
            self.o_stream.first.eq(0),
            self.o_stream.last.eq(0),
            self.i_stream.ready.eq(0),
        ]

        with m.FSM(name="aligner"):
            with m.State("IDLE"):
                # Wait for first beat
                m.d.comb += self.i_stream.ready.eq(1)
                with m.If(self.i_stream.valid & self.i_stream.first):
                    with m.If(self.offset == 0):
                        # Zero offset: pass-through mode
                        m.d.sync += r_offset.eq(0)
                        # Forward this beat directly
                        m.d.comb += [
                            self.o_stream.payload.eq(self.i_stream.payload),
                            self.o_stream.valid.eq(1),
                            self.o_stream.first.eq(1),
                            self.o_stream.last.eq(self.i_stream.last),
                        ]
                        with m.If(self.o_stream.ready):
                            with m.If(self.i_stream.last):
                                m.next = "IDLE"
                            with m.Else():
                                m.next = "PASS"
                        with m.Else():
                            # Downstream not ready, don't consume
                            m.d.comb += self.i_stream.ready.eq(0)
                    with m.Else():
                        # Non-zero offset: store first beat as carry, absorb it
                        m.d.sync += [
                            r_offset.eq(self.offset),
                            carry.eq(self.i_stream.payload),
                            r_first_out.eq(1),
                        ]
                        with m.If(self.i_stream.last):
                            # Single-beat packet with offset: go to flush
                            m.d.sync += r_last_seen.eq(1)
                            m.next = "FLUSH"
                        with m.Else():
                            m.next = "ALIGN"

            with m.State("PASS"):
                # Zero-offset pass-through for remaining beats
                m.d.comb += [
                    self.o_stream.payload.eq(self.i_stream.payload),
                    self.o_stream.valid.eq(self.i_stream.valid),
                    self.o_stream.first.eq(0),
                    self.o_stream.last.eq(self.i_stream.last),
                    self.i_stream.ready.eq(self.o_stream.ready),
                ]
                with m.If(self.i_stream.valid & self.o_stream.ready & self.i_stream.last):
                    m.next = "IDLE"

            with m.State("ALIGN"):
                # Non-zero offset: stitch carry with current beat
                m.d.comb += [
                    self.o_stream.payload.eq(aligned_data),
                    self.o_stream.valid.eq(self.i_stream.valid),
                    self.o_stream.first.eq(r_first_out),
                    self.o_stream.last.eq(0),
                    self.i_stream.ready.eq(self.o_stream.ready),
                ]
                with m.If(self.i_stream.valid & self.o_stream.ready):
                    m.d.sync += [
                        carry.eq(self.i_stream.payload),
                        r_first_out.eq(0),
                    ]
                    with m.If(self.i_stream.last):
                        # Input packet ended; need flush beat for remaining carry
                        m.d.sync += r_last_seen.eq(1)
                        m.next = "FLUSH"

            with m.State("FLUSH"):
                # Emit the remaining carry data as the final beat
                m.d.comb += [
                    self.o_stream.payload.eq(flush_data),
                    self.o_stream.valid.eq(1),
                    self.o_stream.first.eq(r_first_out),
                    self.o_stream.last.eq(1),
                ]
                with m.If(self.o_stream.ready):
                    m.d.sync += [
                        r_first_out.eq(0),
                        r_last_seen.eq(0),
                    ]
                    m.next = "IDLE"

        return m


class WordReorder(wiring.Component):
    """Reorder words within a data beat according to a fixed permutation.

    This is useful for reversing DWORDs in a wide data word (e.g. reversing
    8 DWORDs in a 256-bit word) or performing arbitrary word-level shuffles.

    Parameters
    ----------
    data_width : :class:`int`
        Total data width in bits (e.g. 256).  Must be a multiple of
        *word_width*.
    word_width : :class:`int`
        Width of each word in bits (default 32 for DWORD).
    order : :class:`tuple` of :class:`int`
        Reorder pattern.  ``order[i]`` specifies which input word index
        supplies output word *i*.  For example, ``(7,6,5,4,3,2,1,0)``
        reverses 8 DWORDs.  Length must equal ``data_width // word_width``.
    field : :class:`str`
        Which field to reorder (default ``"dat"``).  Currently only the
        payload (``"dat"``) is supported.

    Ports
    -----
    i_stream : In(signature)
        Input stream.
    o_stream : Out(signature)
        Output stream with reordered words.
    """

    def __init__(self, data_width, word_width=32, *, order, field="dat"):
        if data_width % word_width != 0:
            raise ValueError(
                f"data_width ({data_width}) must be a multiple of "
                f"word_width ({word_width})")
        n_words = data_width // word_width
        if len(order) != n_words:
            raise ValueError(
                f"len(order) must equal data_width // word_width = {n_words}, "
                f"got {len(order)}")
        for idx in order:
            if not (0 <= idx < n_words):
                raise ValueError(
                    f"All values in order must be in range [0, {n_words}), "
                    f"got {idx}")

        self._data_width = data_width
        self._word_width = word_width
        self._order = tuple(order)
        self._field = field
        self._n_words = n_words

        sig = StreamSignature(unsigned(data_width),
                              has_first_last=True, has_keep=True)
        self._stream_sig = sig
        super().__init__({
            "i_stream": In(sig),
            "o_stream": Out(sig),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        ww = self._word_width
        n_words = self._n_words

        # Reorder payload words according to self._order
        reordered_words = []
        for i in range(n_words):
            src_idx = self._order[i]
            reordered_words.append(
                self.i_stream.payload[src_idx * ww:(src_idx + 1) * ww])

        m.d.comb += [
            self.o_stream.payload.eq(Cat(*reordered_words)),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Reorder keep bits: each word has (word_width // 8) keep bits
        bytes_per_word = ww // 8
        reordered_keep = []
        for i in range(n_words):
            src_idx = self._order[i]
            reordered_keep.append(
                self.i_stream.keep[src_idx * bytes_per_word:(src_idx + 1) * bytes_per_word])
        m.d.comb += self.o_stream.keep.eq(Cat(*reordered_keep))

        # Pass through first/last
        if self._stream_sig.has_first_last:
            m.d.comb += [
                self.o_stream.first.eq(self.i_stream.first),
                self.o_stream.last.eq(self.i_stream.last),
            ]

        if self._stream_sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)

        return m
