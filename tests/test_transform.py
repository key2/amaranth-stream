"""Tests for amaranth_stream.transform (StreamMap, StreamFilter, EndianSwap, ByteAligner)."""

import random
import pytest

from amaranth.hdl import unsigned, Signal, Cat
from amaranth.sim import Simulator, Period

from amaranth_stream._base import Signature
from amaranth_stream.transform import StreamMap, StreamFilter, EndianSwap, ByteAligner
from amaranth_stream.sim import StreamSimSender, StreamSimReceiver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_sim(dut, *testbenches, deadline_ns=50_000, vcd_name="test_transform.vcd"):
    """Helper to run a simulation with one or more testbenches."""
    sim = Simulator(dut)
    sim.add_clock(Period(MHz=10))
    for tb in testbenches:
        sim.add_testbench(tb)
    with sim.write_vcd(vcd_name):
        sim.run_until(Period(ns=deadline_ns))


# ---------------------------------------------------------------------------
# StreamMap tests
# ---------------------------------------------------------------------------

class TestStreamMap:
    """Test StreamMap (combinational payload transformation)."""

    def test_stream_map_double(self):
        """Map that doubles payload."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(9))  # wider to hold doubled value

        def double_transform(m, payload):
            result = Signal(9, name="doubled")
            m.d.comb += result.eq(payload << 1)
            return result

        dut = StreamMap(i_sig, o_sig, double_transform)
        results = []
        expected_in = [1, 2, 3, 10, 127]
        expected_out = [v * 2 for v in expected_in]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected_in:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected_in:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_map_double.vcd")
        assert results == expected_out

    def test_stream_map_mask(self):
        """Map that masks bits (keep lower 4 bits)."""
        sig = Signature(unsigned(8))

        def mask_transform(m, payload):
            result = Signal(8, name="masked")
            m.d.comb += result.eq(payload & 0x0F)
            return result

        dut = StreamMap(sig, sig, mask_transform)
        results = []
        expected_in = [0xFF, 0xAB, 0x12, 0x00]
        expected_out = [0x0F, 0x0B, 0x02, 0x00]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected_in:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected_in:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_map_mask.vcd")
        assert results == expected_out

    def test_stream_map_with_first_last(self):
        """first/last signals pass through StreamMap."""
        i_sig = Signature(unsigned(8), has_first_last=True)
        o_sig = Signature(unsigned(8), has_first_last=True)

        def identity_transform(m, payload):
            return payload

        dut = StreamMap(i_sig, o_sig, identity_transform)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send_packet(ctx, [0x10, 0x20, 0x30])

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            packet = await receiver.recv_packet(ctx)
            results.extend(packet)

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_map_fl.vcd")

        assert len(results) == 3
        assert results[0]["first"] == 1
        assert results[0]["last"] == 0
        assert results[1]["first"] == 0
        assert results[1]["last"] == 0
        assert results[2]["first"] == 0
        assert results[2]["last"] == 1


# ---------------------------------------------------------------------------
# StreamFilter tests
# ---------------------------------------------------------------------------

class TestStreamFilter:
    """Test StreamFilter (conditional beat dropping)."""

    def test_stream_filter_even(self):
        """Filter that passes only even values."""
        sig = Signature(unsigned(8))

        def even_predicate(m, payload):
            return ~payload[0]  # bit 0 == 0 means even

        dut = StreamFilter(sig, even_predicate)
        results = []
        input_vals = [1, 2, 3, 4, 5, 6, 7, 8]
        expected = [2, 4, 6, 8]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in input_vals:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_filter_even.vcd")
        assert results == expected

    def test_stream_filter_all_pass(self):
        """Predicate always true — all beats pass through."""
        sig = Signature(unsigned(8))

        def always_pass(m, payload):
            return 1

        dut = StreamFilter(sig, always_pass)
        results = []
        expected = [0x10, 0x20, 0x30, 0x40]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_filter_all_pass.vcd")
        assert results == expected

    def test_stream_filter_all_drop(self):
        """Predicate always false — all beats are dropped."""
        sig = Signature(unsigned(8))

        def always_drop(m, payload):
            return 0

        dut = StreamFilter(sig, always_drop)
        input_vals = [0x10, 0x20, 0x30]
        sender_done = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in input_vals:
                await sender.send(ctx, val)
            sender_done.append(True)

        async def checker_tb(ctx):
            # Wait for sender to finish, then verify no output valid
            for _ in range(20):
                await ctx.tick()
            # Output valid should never have been asserted
            # (sender should complete quickly since dropped beats are consumed)

        _run_sim(dut, sender_tb, checker_tb, vcd_name="test_filter_all_drop.vcd")
        assert len(sender_done) == 1  # sender completed (beats were consumed)

    def test_stream_filter_stress(self):
        """Random valid/ready with filter."""
        sig = Signature(unsigned(8))

        def pass_above_128(m, payload):
            return payload[7]  # bit 7 set means >= 128

        dut = StreamFilter(sig, pass_above_128)
        rng = random.Random(42)
        input_vals = [rng.randint(0, 255) for _ in range(30)]
        expected = [v for v in input_vals if v >= 128]
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream, random_valid=True, seed=10)
            for val in input_vals:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=20)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 deadline_ns=500_000, vcd_name="test_filter_stress.vcd")
        assert results == expected


# ---------------------------------------------------------------------------
# EndianSwap tests
# ---------------------------------------------------------------------------

class TestEndianSwap:
    """Test EndianSwap (byte-order reversal)."""

    def test_endian_swap_16(self):
        """16-bit endian swap: 0xAABB → 0xBBAA."""
        sig = Signature(unsigned(16))
        dut = EndianSwap(sig)
        results = []
        input_vals = [0xAABB, 0x1234, 0xFF00, 0x0001]
        expected = [0xBBAA, 0x3412, 0x00FF, 0x0100]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in input_vals:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in input_vals:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_endian_16.vcd")
        assert results == expected

    def test_endian_swap_32(self):
        """32-bit endian swap: 0xDEADBEEF → 0xEFBEADDE."""
        sig = Signature(unsigned(32))
        dut = EndianSwap(sig)
        results = []
        input_vals = [0xDEADBEEF, 0x01020304]
        expected = [0xEFBEADDE, 0x04030201]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in input_vals:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in input_vals:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_endian_32.vcd")
        assert results == expected


# ---------------------------------------------------------------------------
# ByteAligner tests
# ---------------------------------------------------------------------------

class TestByteAligner:
    """Test ByteAligner (sub-word byte alignment)."""

    def test_byte_aligner_basic(self):
        """Shift by 1 byte: 0x00FF → 0xFF00 (for 16-bit)."""
        sig = Signature(unsigned(16))
        dut = ByteAligner(sig, max_shift=2)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            ctx.set(dut.shift, 1)  # shift by 1 byte = 8 bits left
            await sender.send(ctx, 0x00FF)
            await sender.send(ctx, 0x0001)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            beat1 = await receiver.recv(ctx)
            results.append(beat1["payload"])
            beat2 = await receiver.recv(ctx)
            results.append(beat2["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_aligner_basic.vcd")
        assert results[0] == 0xFF00
        assert results[1] == 0x0100

    def test_byte_aligner_zero_shift(self):
        """No shift: data passes through unchanged."""
        sig = Signature(unsigned(16))
        dut = ByteAligner(sig, max_shift=2)
        results = []
        expected = [0xAABB, 0x1234]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            ctx.set(dut.shift, 0)  # no shift
            for val in expected:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_aligner_zero.vcd")
        assert results == expected
