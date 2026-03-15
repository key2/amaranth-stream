"""Width conversion components for amaranth-stream.

Provides :class:`StreamConverter`, :class:`StrideConverter`, :class:`Gearbox`,
:class:`StreamCast`, :class:`Pack`, and :class:`Unpack` for converting between
streams of different widths.
"""

import math

from amaranth import *
from amaranth.hdl import Shape, ShapeLike, Signal, Cat, Const, ClockDomain, unsigned
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, connect

from ._base import Signature as StreamSignature

__all__ = [
    "StreamConverter",
    "StrideConverter",
    "Gearbox",
    "StreamCast",
    "Pack",
    "Unpack",
]


class StreamConverter(wiring.Component):
    """Integer-ratio width converter for flat payloads.

    Converts between streams where the wider payload width is an exact
    integer multiple of the narrower payload width.

    Parameters
    ----------
    i_signature : :class:`~amaranth_stream.Signature`
        Input stream signature.
    o_signature : :class:`~amaranth_stream.Signature`
        Output stream signature.

    Ports
    -----
    i_stream : In(i_signature)
        Input stream.
    o_stream : Out(o_signature)
        Output stream.
    """

    def __init__(self, i_signature, o_signature):
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

        i_width = i_signature.payload_width
        o_width = o_signature.payload_width

        if i_width == o_width:
            self._mode = "identity"
            self._ratio = 1
        elif o_width > i_width:
            if o_width % i_width != 0:
                raise ValueError(
                    f"Output width ({o_width}) must be an integer multiple "
                    f"of input width ({i_width})")
            self._mode = "upsize"
            self._ratio = o_width // i_width
        else:
            if i_width % o_width != 0:
                raise ValueError(
                    f"Input width ({i_width}) must be an integer multiple "
                    f"of output width ({o_width})")
            self._mode = "downsize"
            self._ratio = i_width // o_width

        super().__init__({
            "i_stream": In(i_signature),
            "o_stream": Out(o_signature),
        })

    def elaborate(self, platform):
        m = Module()

        if self._mode == "identity":
            return self._elaborate_identity(m)
        elif self._mode == "upsize":
            return self._elaborate_upsize(m)
        else:
            return self._elaborate_downsize(m)

    def _elaborate_identity(self, m):
        """Wire-through for same-width streams."""
        m.domains += ClockDomain("sync")
        m.d.comb += [
            self.o_stream.payload.eq(self.i_stream.payload),
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]
        if self._i_sig.has_first_last and self._o_sig.has_first_last:
            m.d.comb += [
                self.o_stream.first.eq(self.i_stream.first),
                self.o_stream.last.eq(self.i_stream.last),
            ]
        if self._i_sig.has_keep and self._o_sig.has_keep:
            m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)
        if self._i_sig.param_shape is not None and self._o_sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)
        return m

    def _elaborate_upsize(self, m):
        """Collect ratio narrow input beats into one wide output beat."""
        ratio = self._ratio
        i_width = self._i_sig.payload_width
        o_width = self._o_sig.payload_width

        counter = Signal(range(ratio))
        shift_reg = Signal(o_width)
        output_valid = Signal()

        # Optional signal storage
        has_fl = self._i_sig.has_first_last and self._o_sig.has_first_last
        has_keep_io = self._i_sig.has_keep and self._o_sig.has_keep

        if has_fl:
            first_reg = Signal()
            last_reg = Signal()
        if has_keep_io:
            i_keep_width = math.ceil(i_width / 8)
            o_keep_width = math.ceil(o_width / 8)
            keep_reg = Signal(o_keep_width)

        # Accept input when output is not valid, or when output is being consumed
        m.d.comb += self.i_stream.ready.eq(~output_valid | (output_valid & self.o_stream.ready))

        with m.If(self.i_stream.valid & self.i_stream.ready):
            # Store input data into shift register at the correct position
            for i in range(ratio):
                with m.If(counter == i):
                    m.d.sync += shift_reg[i * i_width:(i + 1) * i_width].eq(
                        self.i_stream.payload)

            if has_fl:
                # Capture first from the first beat
                with m.If(counter == 0):
                    m.d.sync += first_reg.eq(self.i_stream.first)
                # Capture last from the last beat
                with m.If(counter == ratio - 1):
                    m.d.sync += last_reg.eq(self.i_stream.last)

            if has_keep_io:
                for i in range(ratio):
                    with m.If(counter == i):
                        m.d.sync += keep_reg[i * i_keep_width:(i + 1) * i_keep_width].eq(
                            self.i_stream.keep)

            with m.If(counter == ratio - 1):
                m.d.sync += [
                    counter.eq(0),
                    output_valid.eq(1),
                ]
            with m.Else():
                m.d.sync += counter.eq(counter + 1)

        # When output is consumed, clear valid
        with m.If(output_valid & self.o_stream.ready):
            m.d.sync += output_valid.eq(0)

        # Drive output
        m.d.comb += [
            self.o_stream.payload.eq(shift_reg),
            self.o_stream.valid.eq(output_valid),
        ]
        if has_fl:
            m.d.comb += [
                self.o_stream.first.eq(first_reg),
                self.o_stream.last.eq(last_reg),
            ]
        if has_keep_io:
            m.d.comb += self.o_stream.keep.eq(keep_reg)

        return m

    def _elaborate_downsize(self, m):
        """Split one wide input beat into ratio narrow output beats."""
        ratio = self._ratio
        i_width = self._i_sig.payload_width
        o_width = self._o_sig.payload_width

        counter = Signal(range(ratio))
        shift_reg = Signal(i_width)
        active = Signal()  # We have data to output

        has_fl = self._i_sig.has_first_last and self._o_sig.has_first_last
        has_keep_io = self._i_sig.has_keep and self._o_sig.has_keep

        if has_fl:
            first_reg = Signal()
            last_reg = Signal()
        if has_keep_io:
            i_keep_width = math.ceil(i_width / 8)
            o_keep_width = math.ceil(o_width / 8)
            keep_reg = Signal(i_keep_width)

        # Accept input only when we're not actively outputting
        m.d.comb += self.i_stream.ready.eq(~active)

        # Latch input
        with m.If(self.i_stream.valid & self.i_stream.ready):
            m.d.sync += [
                shift_reg.eq(self.i_stream.payload),
                counter.eq(0),
                active.eq(1),
            ]
            if has_fl:
                m.d.sync += [
                    first_reg.eq(self.i_stream.first),
                    last_reg.eq(self.i_stream.last),
                ]
            if has_keep_io:
                m.d.sync += keep_reg.eq(self.i_stream.keep)

        # Output the current slice
        for i in range(ratio):
            with m.If(counter == i):
                m.d.comb += self.o_stream.payload.eq(
                    shift_reg[i * o_width:(i + 1) * o_width])
                if has_keep_io:
                    m.d.comb += self.o_stream.keep.eq(
                        keep_reg[i * o_keep_width:(i + 1) * o_keep_width])

        m.d.comb += self.o_stream.valid.eq(active)

        if has_fl:
            m.d.comb += [
                self.o_stream.first.eq(first_reg & (counter == 0)),
                self.o_stream.last.eq(last_reg & (counter == ratio - 1)),
            ]

        # Advance counter on output handshake
        with m.If(active & self.o_stream.valid & self.o_stream.ready):
            with m.If(counter == ratio - 1):
                m.d.sync += active.eq(0)
            with m.Else():
                m.d.sync += counter.eq(counter + 1)

        return m


class StrideConverter(wiring.Component):
    """Structured field-aware width converter.

    Handles non-integer ratios by padding to LCM. For integer ratios,
    delegates to :class:`StreamConverter` logic.

    Parameters
    ----------
    i_signature : :class:`~amaranth_stream.Signature`
        Input stream signature.
    o_signature : :class:`~amaranth_stream.Signature`
        Output stream signature.

    Ports
    -----
    i_stream : In(i_signature)
        Input stream.
    o_stream : Out(o_signature)
        Output stream.
    """

    def __init__(self, i_signature, o_signature):
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

        i_width = i_signature.payload_width
        o_width = o_signature.payload_width

        # Compute LCM to determine padding needed
        lcm_width = math.lcm(i_width, o_width)
        self._lcm_width = lcm_width
        self._i_ratio = lcm_width // i_width  # input beats per LCM
        self._o_ratio = lcm_width // o_width  # output beats per LCM

        super().__init__({
            "i_stream": In(i_signature),
            "o_stream": Out(o_signature),
        })

    def elaborate(self, platform):
        m = Module()

        i_width = self._i_sig.payload_width
        o_width = self._o_sig.payload_width
        lcm_width = self._lcm_width
        i_ratio = self._i_ratio
        o_ratio = self._o_ratio

        if i_width == o_width:
            # Identity: wire-through
            m.domains += ClockDomain("sync")
            m.d.comb += [
                self.o_stream.payload.eq(self.i_stream.payload),
                self.o_stream.valid.eq(self.i_stream.valid),
                self.i_stream.ready.eq(self.o_stream.ready),
            ]
            if self._i_sig.has_first_last and self._o_sig.has_first_last:
                m.d.comb += [
                    self.o_stream.first.eq(self.i_stream.first),
                    self.o_stream.last.eq(self.i_stream.last),
                ]
            if self._i_sig.has_keep and self._o_sig.has_keep:
                m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)
            return m

        # General case: collect i_ratio input beats into LCM buffer,
        # then output o_ratio output beats from it.
        buf = Signal(lcm_width)
        i_counter = Signal(range(i_ratio))
        o_counter = Signal(range(o_ratio))

        # States: FILL (collecting input), DRAIN (outputting)
        with m.FSM():
            with m.State("FILL"):
                m.d.comb += self.i_stream.ready.eq(1)
                m.d.comb += self.o_stream.valid.eq(0)

                with m.If(self.i_stream.valid & self.i_stream.ready):
                    for i in range(i_ratio):
                        with m.If(i_counter == i):
                            m.d.sync += buf[i * i_width:(i + 1) * i_width].eq(
                                self.i_stream.payload)

                    with m.If(i_counter == i_ratio - 1):
                        m.d.sync += [
                            i_counter.eq(0),
                            o_counter.eq(0),
                        ]
                        m.next = "DRAIN"
                    with m.Else():
                        m.d.sync += i_counter.eq(i_counter + 1)

            with m.State("DRAIN"):
                m.d.comb += self.i_stream.ready.eq(0)
                m.d.comb += self.o_stream.valid.eq(1)

                for i in range(o_ratio):
                    with m.If(o_counter == i):
                        m.d.comb += self.o_stream.payload.eq(
                            buf[i * o_width:(i + 1) * o_width])

                with m.If(self.o_stream.valid & self.o_stream.ready):
                    with m.If(o_counter == o_ratio - 1):
                        m.d.sync += o_counter.eq(0)
                        m.next = "FILL"
                    with m.Else():
                        m.d.sync += o_counter.eq(o_counter + 1)

        return m


class Gearbox(wiring.Component):
    """Non-integer ratio width converter using shift-register approach.

    Converts between streams of arbitrary widths (e.g. 10b→8b or 8b→10b)
    using a shift register buffer.

    Parameters
    ----------
    i_width : :class:`int`
        Input data width in bits.
    o_width : :class:`int`
        Output data width in bits.
    has_first_last : :class:`bool`
        If ``True``, include first/last framing signals.

    Ports
    -----
    i_stream : In(Signature(i_width))
        Input stream.
    o_stream : Out(Signature(o_width))
        Output stream.
    """

    def __init__(self, i_width, o_width, *, has_first_last=False):
        self._i_width = i_width
        self._o_width = o_width
        self._has_first_last = has_first_last

        i_sig = StreamSignature(i_width, has_first_last=has_first_last)
        o_sig = StreamSignature(o_width, has_first_last=has_first_last)

        super().__init__({
            "i_stream": In(i_sig),
            "o_stream": Out(o_sig),
        })

    def elaborate(self, platform):
        m = Module()

        i_width = self._i_width
        o_width = self._o_width
        lcm_w = math.lcm(i_width, o_width)

        # Number of input/output positions within one LCM cycle
        n_in = lcm_w // i_width
        n_out = lcm_w // o_width

        # Buffer to hold one full LCM cycle of data
        buf = Signal(lcm_w)

        # Counters for input and output positions within the LCM cycle
        i_counter = Signal(range(n_in))
        o_counter = Signal(range(n_out))

        # Level tracks how many valid bits are in the buffer
        level = Signal(range(lcm_w + max(i_width, o_width) + 1))

        # Can accept input: enough space
        can_write = Signal()
        m.d.comb += can_write.eq(level + i_width <= lcm_w)

        # Can produce output: enough data
        can_read = Signal()
        m.d.comb += can_read.eq(level >= o_width)

        # Handshake
        m.d.comb += self.i_stream.ready.eq(can_write)
        m.d.comb += self.o_stream.valid.eq(can_read)

        # Write: store i_width bits at position determined by i_counter
        do_write = Signal()
        do_read = Signal()
        m.d.comb += [
            do_write.eq(self.i_stream.valid & self.i_stream.ready),
            do_read.eq(self.o_stream.valid & self.o_stream.ready),
        ]

        with m.If(do_write):
            for idx in range(n_in):
                with m.If(i_counter == idx):
                    m.d.sync += buf[idx * i_width:(idx + 1) * i_width].eq(
                        self.i_stream.payload)
            with m.If(i_counter == n_in - 1):
                m.d.sync += i_counter.eq(0)
            with m.Else():
                m.d.sync += i_counter.eq(i_counter + 1)

        # Read: extract o_width bits at position determined by o_counter
        for idx in range(n_out):
            with m.If(o_counter == idx):
                m.d.comb += self.o_stream.payload.eq(
                    buf[idx * o_width:(idx + 1) * o_width])

        with m.If(do_read):
            with m.If(o_counter == n_out - 1):
                m.d.sync += o_counter.eq(0)
            with m.Else():
                m.d.sync += o_counter.eq(o_counter + 1)

        # Update level
        with m.If(do_write & do_read):
            m.d.sync += level.eq(level + i_width - o_width)
        with m.Elif(do_write):
            m.d.sync += level.eq(level + i_width)
        with m.Elif(do_read):
            m.d.sync += level.eq(level - o_width)

        return m


class StreamCast(wiring.Component):
    """Zero-cost bit reinterpretation between streams of the same bit width.

    Simply wires input payload bits to output payload bits with a different
    shape interpretation. Passes through valid/ready/first/last/param/keep
    unchanged.

    Parameters
    ----------
    i_signature : :class:`~amaranth_stream.Signature`
        Input stream signature.
    o_signature : :class:`~amaranth_stream.Signature`
        Output stream signature (must have same payload bit width).

    Ports
    -----
    i_stream : In(i_signature)
        Input stream.
    o_stream : Out(o_signature)
        Output stream.
    """

    def __init__(self, i_signature, o_signature):
        if not isinstance(i_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature for i_signature, "
                f"got {type(i_signature).__name__}")
        if not isinstance(o_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature for o_signature, "
                f"got {type(o_signature).__name__}")

        i_width = i_signature.payload_width
        o_width = o_signature.payload_width
        if i_width != o_width:
            raise ValueError(
                f"StreamCast requires same payload bit width, "
                f"got input={i_width}, output={o_width}")

        self._i_sig = i_signature
        self._o_sig = o_signature

        super().__init__({
            "i_stream": In(i_signature),
            "o_stream": Out(o_signature),
        })

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain("sync")

        # Wire payload bits directly (reinterpret cast)
        i_width = self._i_sig.payload_width
        for bit in range(i_width):
            m.d.comb += self.o_stream.payload[bit].eq(self.i_stream.payload[bit])

        # Pass through handshake
        m.d.comb += [
            self.o_stream.valid.eq(self.i_stream.valid),
            self.i_stream.ready.eq(self.o_stream.ready),
        ]

        # Pass through optional signals
        if self._i_sig.has_first_last and self._o_sig.has_first_last:
            m.d.comb += [
                self.o_stream.first.eq(self.i_stream.first),
                self.o_stream.last.eq(self.i_stream.last),
            ]
        if self._i_sig.has_keep and self._o_sig.has_keep:
            m.d.comb += self.o_stream.keep.eq(self.i_stream.keep)
        if self._i_sig.param_shape is not None and self._o_sig.param_shape is not None:
            m.d.comb += self.o_stream.param.eq(self.i_stream.param)

        return m


class Pack(wiring.Component):
    """Collects N narrow beats into 1 wide beat.

    The output payload is ``ArrayLayout(payload_shape, n)`` — an array of
    N elements, each with the input payload shape.

    Parameters
    ----------
    i_signature : :class:`~amaranth_stream.Signature`
        Input (narrow) stream signature.
    n : :class:`int`
        Number of beats to pack.

    Ports
    -----
    i_stream : In(i_signature)
        Input stream (narrow).
    o_stream : Out(o_signature)
        Output stream (wide, ArrayLayout payload).
    """

    def __init__(self, i_signature, n):
        if not isinstance(i_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature for i_signature, "
                f"got {type(i_signature).__name__}")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")

        self._i_sig = i_signature
        self._n = n

        i_shape = Shape.cast(i_signature.payload_shape)
        o_payload_width = i_shape.width * n

        has_fl = i_signature.has_first_last
        has_keep = i_signature.has_keep

        o_sig = StreamSignature(
            unsigned(o_payload_width),
            has_first_last=has_fl,
            has_keep=has_keep,
            param_shape=i_signature.param_shape,
        )
        self._o_sig = o_sig

        super().__init__({
            "i_stream": In(i_signature),
            "o_stream": Out(o_sig),
        })

    def elaborate(self, platform):
        m = Module()

        n = self._n
        i_width = self._i_sig.payload_width
        o_width = self._o_sig.payload_width

        counter = Signal(range(n))
        shift_reg = Signal(o_width)
        output_valid = Signal()

        has_fl = self._i_sig.has_first_last and self._o_sig.has_first_last
        has_keep_io = self._i_sig.has_keep and self._o_sig.has_keep

        if has_fl:
            first_reg = Signal()
            last_reg = Signal()
        if has_keep_io:
            i_keep_width = max(1, math.ceil(i_width / 8))
            o_keep_width = max(1, math.ceil(o_width / 8))
            keep_reg = Signal(o_keep_width)

        # Accept input when output is not valid, or when output is being consumed
        m.d.comb += self.i_stream.ready.eq(~output_valid | (output_valid & self.o_stream.ready))

        with m.If(self.i_stream.valid & self.i_stream.ready):
            for i in range(n):
                with m.If(counter == i):
                    m.d.sync += shift_reg[i * i_width:(i + 1) * i_width].eq(
                        self.i_stream.payload)

            if has_fl:
                with m.If(counter == 0):
                    m.d.sync += first_reg.eq(self.i_stream.first)
                with m.If(counter == n - 1):
                    m.d.sync += last_reg.eq(self.i_stream.last)

            if has_keep_io:
                for i in range(n):
                    with m.If(counter == i):
                        m.d.sync += keep_reg[i * i_keep_width:(i + 1) * i_keep_width].eq(
                            self.i_stream.keep)

            with m.If(counter == n - 1):
                m.d.sync += [
                    counter.eq(0),
                    output_valid.eq(1),
                ]
            with m.Else():
                m.d.sync += counter.eq(counter + 1)

        with m.If(output_valid & self.o_stream.ready):
            m.d.sync += output_valid.eq(0)

        m.d.comb += [
            self.o_stream.payload.eq(shift_reg),
            self.o_stream.valid.eq(output_valid),
        ]
        if has_fl:
            m.d.comb += [
                self.o_stream.first.eq(first_reg),
                self.o_stream.last.eq(last_reg),
            ]
        if has_keep_io:
            m.d.comb += self.o_stream.keep.eq(keep_reg)

        return m


class Unpack(wiring.Component):
    """Splits 1 wide beat into N narrow beats.

    The input payload is ``ArrayLayout(payload_shape, n)`` — an array of
    N elements, each with the output payload shape.

    Parameters
    ----------
    o_signature : :class:`~amaranth_stream.Signature`
        Output (narrow) stream signature.
    n : :class:`int`
        Number of beats to unpack.

    Ports
    -----
    i_stream : In(i_signature)
        Input stream (wide, ArrayLayout payload).
    o_stream : Out(o_signature)
        Output stream (narrow).
    """

    def __init__(self, o_signature, n):
        if not isinstance(o_signature, StreamSignature):
            raise TypeError(
                f"Expected amaranth_stream.Signature for o_signature, "
                f"got {type(o_signature).__name__}")
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")

        self._o_sig = o_signature
        self._n = n

        o_shape = Shape.cast(o_signature.payload_shape)
        i_payload_width = o_shape.width * n

        has_fl = o_signature.has_first_last
        has_keep = o_signature.has_keep

        i_sig = StreamSignature(
            unsigned(i_payload_width),
            has_first_last=has_fl,
            has_keep=has_keep,
            param_shape=o_signature.param_shape,
        )
        self._i_sig = i_sig

        super().__init__({
            "i_stream": In(i_sig),
            "o_stream": Out(o_signature),
        })

    def elaborate(self, platform):
        m = Module()

        n = self._n
        i_width = self._i_sig.payload_width
        o_width = self._o_sig.payload_width

        counter = Signal(range(n))
        shift_reg = Signal(i_width)
        active = Signal()

        has_fl = self._i_sig.has_first_last and self._o_sig.has_first_last
        has_keep_io = self._i_sig.has_keep and self._o_sig.has_keep

        if has_fl:
            first_reg = Signal()
            last_reg = Signal()
        if has_keep_io:
            i_keep_width = max(1, math.ceil(i_width / 8))
            o_keep_width = max(1, math.ceil(o_width / 8))
            keep_reg = Signal(i_keep_width)

        # Accept input only when not actively outputting
        m.d.comb += self.i_stream.ready.eq(~active)

        # Latch input
        with m.If(self.i_stream.valid & self.i_stream.ready):
            m.d.sync += [
                shift_reg.eq(self.i_stream.payload),
                counter.eq(0),
                active.eq(1),
            ]
            if has_fl:
                m.d.sync += [
                    first_reg.eq(self.i_stream.first),
                    last_reg.eq(self.i_stream.last),
                ]
            if has_keep_io:
                m.d.sync += keep_reg.eq(self.i_stream.keep)

        # Output the current slice
        for i in range(n):
            with m.If(counter == i):
                m.d.comb += self.o_stream.payload.eq(
                    shift_reg[i * o_width:(i + 1) * o_width])
                if has_keep_io:
                    m.d.comb += self.o_stream.keep.eq(
                        keep_reg[i * o_keep_width:(i + 1) * o_keep_width])

        m.d.comb += self.o_stream.valid.eq(active)

        if has_fl:
            m.d.comb += [
                self.o_stream.first.eq(first_reg & (counter == 0)),
                self.o_stream.last.eq(last_reg & (counter == n - 1)),
            ]

        # Advance counter on output handshake
        with m.If(active & self.o_stream.valid & self.o_stream.ready):
            with m.If(counter == n - 1):
                m.d.sync += active.eq(0)
            with m.Else():
                m.d.sync += counter.eq(counter + 1)

        return m
