"""Tests for amaranth_stream.converter (StreamConverter, StrideConverter,
Gearbox, StreamCast, Pack, Unpack)."""

import random
import pytest

from amaranth.hdl import unsigned, Shape
from amaranth.lib import data
from amaranth.sim import Simulator, Period

from amaranth_stream._base import Signature
from amaranth_stream.converter import (
    StreamConverter,
    StrideConverter,
    Gearbox,
    StreamCast,
    Pack,
    Unpack,
)
from amaranth_stream.sim import StreamSimSender, StreamSimReceiver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_sim(dut, *testbenches, deadline_ns=100_000, vcd_name=None):
    """Helper to run a simulation with one or more testbenches."""
    sim = Simulator(dut)
    sim.add_clock(Period(MHz=10))
    for tb in testbenches:
        sim.add_testbench(tb)
    if vcd_name:
        with sim.write_vcd(vcd_name):
            sim.run_until(Period(ns=deadline_ns))
    else:
        sim.run_until(Period(ns=deadline_ns))


def _payload_int(val):
    """Convert a payload value to int, handling ArrayLayout views."""
    return int(val)


# ---------------------------------------------------------------------------
# StreamConverter tests
# ---------------------------------------------------------------------------

class TestStreamConverterUpsize:
    """Test StreamConverter upsizing (narrow → wide)."""

    def test_upsize_8_to_32(self):
        """4 narrow 8-bit beats → 1 wide 32-bit beat."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(32))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            # Send 4 bytes: 0x11, 0x22, 0x33, 0x44
            for val in [0x11, 0x22, 0x33, 0x44]:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            beat = await receiver.recv(ctx)
            results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_upsize_8_to_32.vcd")

        # Bytes packed little-endian: 0x44332211
        assert results == [0x44332211]

    def test_upsize_8_to_16(self):
        """2 narrow 8-bit beats → 1 wide 16-bit beat."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(16))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in [0xAB, 0xCD]:
                await sender.send(ctx, val)
            for val in [0x12, 0x34]:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(2):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_upsize_8_to_16.vcd")

        assert results == [0xCDAB, 0x3412]

    def test_upsize_multiple_words(self):
        """Multiple upsized words in sequence."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(32))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            # Word 1: 0x04030201
            for val in [0x01, 0x02, 0x03, 0x04]:
                await sender.send(ctx, val)
            # Word 2: 0x08070605
            for val in [0x05, 0x06, 0x07, 0x08]:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(2):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_upsize_multi.vcd")

        assert results == [0x04030201, 0x08070605]


class TestStreamConverterDownsize:
    """Test StreamConverter downsizing (wide → narrow)."""

    def test_downsize_32_to_8(self):
        """1 wide 32-bit beat → 4 narrow 8-bit beats."""
        i_sig = Signature(unsigned(32))
        o_sig = Signature(unsigned(8))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0x44332211)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(4):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_downsize_32_to_8.vcd")

        # Bytes extracted little-endian
        assert results == [0x11, 0x22, 0x33, 0x44]

    def test_downsize_16_to_8(self):
        """1 wide 16-bit beat → 2 narrow 8-bit beats."""
        i_sig = Signature(unsigned(16))
        o_sig = Signature(unsigned(8))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0xCDAB)
            await sender.send(ctx, 0x3412)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(4):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_downsize_16_to_8.vcd")

        assert results == [0xAB, 0xCD, 0x12, 0x34]

    def test_downsize_multiple_words(self):
        """Multiple downsized words in sequence."""
        i_sig = Signature(unsigned(32))
        o_sig = Signature(unsigned(8))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0x04030201)
            await sender.send(ctx, 0x08070605)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(8):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_downsize_multi.vcd")

        assert results == [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]


class TestStreamConverterIdentity:
    """Test StreamConverter identity (same width)."""

    def test_identity(self):
        """Same width: wire-through."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(8))
        dut = StreamConverter(i_sig, o_sig)
        results = []
        expected = [0x11, 0x22, 0x33, 0x44]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_identity.vcd")

        assert results == expected


class TestStreamConverterFirstLast:
    """Test first/last propagation through StreamConverter."""

    def test_upsize_with_first_last(self):
        """first/last propagation during upsizing."""
        i_sig = Signature(unsigned(8), has_first_last=True)
        o_sig = Signature(unsigned(16), has_first_last=True)
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            # Send 2 beats with first on beat 0, last on beat 1
            await sender.send(ctx, 0xAA, first=1, last=0)
            await sender.send(ctx, 0xBB, first=0, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            beat = await receiver.recv(ctx)
            results.append(beat)

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_upsize_fl.vcd")

        assert len(results) == 1
        assert results[0]["payload"] == 0xBBAA
        assert results[0]["first"] == 1
        assert results[0]["last"] == 1

    def test_downsize_with_first_last(self):
        """first/last propagation during downsizing."""
        i_sig = Signature(unsigned(16), has_first_last=True)
        o_sig = Signature(unsigned(8), has_first_last=True)
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0xBBAA, first=1, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(2):
                beat = await receiver.recv(ctx)
                results.append(beat)

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_downsize_fl.vcd")

        assert len(results) == 2
        assert results[0]["payload"] == 0xAA
        assert results[0]["first"] == 1
        assert results[0]["last"] == 0
        assert results[1]["payload"] == 0xBB
        assert results[1]["first"] == 0
        assert results[1]["last"] == 1


class TestStreamConverterBackpressure:
    """Test backpressure handling in StreamConverter."""

    def test_upsize_backpressure(self):
        """Upsizing with random backpressure."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(32))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        # Send 3 words = 12 bytes
        input_data = list(range(1, 13))
        expected_words = [
            0x04030201,
            0x08070605,
            0x0C0B0A09,
        ]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream, random_valid=True, seed=42)
            for val in input_data:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=99)
            for _ in range(3):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_upsize_bp.vcd")

        assert results == expected_words

    def test_downsize_backpressure(self):
        """Downsizing with random backpressure."""
        i_sig = Signature(unsigned(32))
        o_sig = Signature(unsigned(8))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream, random_valid=True, seed=42)
            await sender.send(ctx, 0x04030201)
            await sender.send(ctx, 0x08070605)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=99)
            for _ in range(8):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_downsize_bp.vcd")

        assert results == [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]


class TestStreamConverterStress:
    """Stress tests for StreamConverter."""

    def test_stress_upsize(self):
        """Random valid/ready stress test for upsizing."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(32))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        rng = random.Random(123)
        # 10 words = 40 bytes
        input_bytes = [rng.randint(0, 255) for _ in range(40)]
        expected_words = []
        for i in range(0, 40, 4):
            word = (input_bytes[i] |
                    (input_bytes[i+1] << 8) |
                    (input_bytes[i+2] << 16) |
                    (input_bytes[i+3] << 24))
            expected_words.append(word)

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream, random_valid=True, seed=200)
            for val in input_bytes:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=300)
            for _ in range(10):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=500_000,
                 vcd_name="test_stress_upsize.vcd")

        assert results == expected_words

    def test_stress_downsize(self):
        """Random valid/ready stress test for downsizing."""
        i_sig = Signature(unsigned(32))
        o_sig = Signature(unsigned(8))
        dut = StreamConverter(i_sig, o_sig)
        results = []

        rng = random.Random(456)
        input_words = [rng.randint(0, 0xFFFFFFFF) for _ in range(10)]
        expected_bytes = []
        for word in input_words:
            expected_bytes.append(word & 0xFF)
            expected_bytes.append((word >> 8) & 0xFF)
            expected_bytes.append((word >> 16) & 0xFF)
            expected_bytes.append((word >> 24) & 0xFF)

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream, random_valid=True, seed=201)
            for val in input_words:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=301)
            for _ in range(40):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=500_000,
                 vcd_name="test_stress_downsize.vcd")

        assert results == expected_bytes


class TestStreamConverterValidation:
    """Test constructor validation for StreamConverter."""

    def test_rejects_non_integer_ratio(self):
        """Non-integer ratio raises ValueError."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(12))
        with pytest.raises(ValueError, match="integer multiple"):
            StreamConverter(i_sig, o_sig)

    def test_rejects_non_signature_input(self):
        with pytest.raises(TypeError, match="amaranth_stream.Signature"):
            StreamConverter("not a sig", Signature(unsigned(8)))

    def test_rejects_non_signature_output(self):
        with pytest.raises(TypeError, match="amaranth_stream.Signature"):
            StreamConverter(Signature(unsigned(8)), "not a sig")


# ---------------------------------------------------------------------------
# Gearbox tests
# ---------------------------------------------------------------------------

class TestGearbox:
    """Test Gearbox (non-integer ratio width converter)."""

    def test_gearbox_10_to_8(self):
        """10-bit input → 8-bit output (LCM=40, 4 in → 5 out)."""
        dut = Gearbox(10, 8)
        results = []

        # 4 x 10-bit values = 40 bits → 5 x 8-bit values
        # Input: 0x3FF, 0x000, 0x155, 0x2AA (10-bit values)
        # Pack as 40 bits: 0x3FF | (0x000 << 10) | (0x155 << 20) | (0x2AA << 30)
        # = 0x3FF + 0 + 0x15500000 + 0xAA800000000 (but only 40 bits)
        # Let's use simpler values
        input_vals = [0b0000000001, 0b0000000010, 0b0000000100, 0b0000001000]
        # 40 bits: 01_00000010_00000001_00000100_00001000 (reversed bit order)
        # Actually: val0[9:0] | val1[9:0] | val2[9:0] | val3[9:0]
        # = 0000000001 | 0000000010 | 0000000100 | 0000001000
        # As 40-bit number: 0000001000_0000000100_0000000010_0000000001
        # Split into 8-bit: 00000001, 00001000, 00000001, 00010000, 00000010
        # Let me compute properly:
        combined = (input_vals[0] |
                    (input_vals[1] << 10) |
                    (input_vals[2] << 20) |
                    (input_vals[3] << 30))
        expected = []
        for i in range(5):
            expected.append((combined >> (i * 8)) & 0xFF)

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in input_vals:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(5):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_gearbox_10_to_8.vcd")

        assert results == expected

    def test_gearbox_8_to_10(self):
        """8-bit input → 10-bit output (LCM=40, 5 in → 4 out)."""
        dut = Gearbox(8, 10)
        results = []

        # 5 x 8-bit values = 40 bits → 4 x 10-bit values
        input_vals = [0x01, 0x02, 0x03, 0x04, 0x05]
        combined = 0
        for i, v in enumerate(input_vals):
            combined |= v << (i * 8)
        expected = []
        for i in range(4):
            expected.append((combined >> (i * 10)) & 0x3FF)

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in input_vals:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(4):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_gearbox_8_to_10.vcd")

        assert results == expected

    def test_gearbox_same_width(self):
        """Same width gearbox acts as pass-through."""
        dut = Gearbox(8, 8)
        results = []
        expected = [0x11, 0x22, 0x33]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_gearbox_same.vcd")

        assert results == expected


# ---------------------------------------------------------------------------
# StreamCast tests
# ---------------------------------------------------------------------------

class TestStreamCast:
    """Test StreamCast (zero-cost bit reinterpretation)."""

    def test_cast_basic(self):
        """Reinterpret 16-bit unsigned as 16-bit unsigned (different shapes)."""
        i_sig = Signature(unsigned(16))
        o_sig = Signature(unsigned(16))
        dut = StreamCast(i_sig, o_sig)
        results = []
        expected = [0x1234, 0xABCD, 0x0000, 0xFFFF]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_cast_basic.vcd")

        assert results == expected

    def test_cast_with_first_last(self):
        """first/last pass through cast."""
        i_sig = Signature(unsigned(8), has_first_last=True)
        o_sig = Signature(unsigned(8), has_first_last=True)
        dut = StreamCast(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0xAA, first=1, last=0)
            await sender.send(ctx, 0xBB, first=0, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(2):
                beat = await receiver.recv(ctx)
                results.append(beat)

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_cast_fl.vcd")

        assert results[0]["payload"] == 0xAA
        assert results[0]["first"] == 1
        assert results[0]["last"] == 0
        assert results[1]["payload"] == 0xBB
        assert results[1]["first"] == 0
        assert results[1]["last"] == 1

    def test_cast_rejects_different_width(self):
        """StreamCast rejects different payload widths."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(16))
        with pytest.raises(ValueError, match="same payload bit width"):
            StreamCast(i_sig, o_sig)


# ---------------------------------------------------------------------------
# Pack tests
# ---------------------------------------------------------------------------

class TestPack:
    """Test Pack (collect N narrow beats into 1 wide beat)."""

    def test_pack_4(self):
        """Pack 4 x 8-bit beats into 1 x 32-bit beat."""
        i_sig = Signature(unsigned(8))
        dut = Pack(i_sig, 4)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in [0x11, 0x22, 0x33, 0x44]:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            beat = await receiver.recv(ctx)
            results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_pack_4.vcd")

        # Packed as: elem[0] in LSBs
        assert results == [0x44332211]

    def test_pack_2(self):
        """Pack 2 x 8-bit beats into 1 x 16-bit beat."""
        i_sig = Signature(unsigned(8))
        dut = Pack(i_sig, 2)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in [0xAB, 0xCD, 0x12, 0x34]:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(2):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_pack_2.vcd")

        assert results == [0xCDAB, 0x3412]

    def test_pack_with_first_last(self):
        """Pack with first/last propagation."""
        i_sig = Signature(unsigned(8), has_first_last=True)
        dut = Pack(i_sig, 2)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0xAA, first=1, last=0)
            await sender.send(ctx, 0xBB, first=0, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            beat = await receiver.recv(ctx)
            results.append(beat)

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_pack_fl.vcd")

        assert results[0]["payload"] == 0xBBAA
        assert results[0]["first"] == 1
        assert results[0]["last"] == 1

    def test_pack_backpressure(self):
        """Pack with random backpressure."""
        i_sig = Signature(unsigned(8))
        dut = Pack(i_sig, 4)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream, random_valid=True, seed=42)
            for val in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=99)
            for _ in range(2):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_pack_bp.vcd")

        assert results == [0x04030201, 0x08070605]


# ---------------------------------------------------------------------------
# Unpack tests
# ---------------------------------------------------------------------------

class TestUnpack:
    """Test Unpack (split 1 wide beat into N narrow beats)."""

    def test_unpack_4(self):
        """Unpack 1 x 32-bit beat into 4 x 8-bit beats."""
        o_sig = Signature(unsigned(8))
        dut = Unpack(o_sig, 4)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0x44332211)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(4):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_unpack_4.vcd")

        assert results == [0x11, 0x22, 0x33, 0x44]

    def test_unpack_2(self):
        """Unpack 1 x 16-bit beat into 2 x 8-bit beats."""
        o_sig = Signature(unsigned(8))
        dut = Unpack(o_sig, 2)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0xCDAB)
            await sender.send(ctx, 0x3412)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(4):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_unpack_2.vcd")

        assert results == [0xAB, 0xCD, 0x12, 0x34]

    def test_unpack_with_first_last(self):
        """Unpack with first/last propagation."""
        o_sig = Signature(unsigned(8), has_first_last=True)
        dut = Unpack(o_sig, 2)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send(ctx, 0xBBAA, first=1, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(2):
                beat = await receiver.recv(ctx)
                results.append(beat)

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_unpack_fl.vcd")

        assert results[0]["payload"] == 0xAA
        assert results[0]["first"] == 1
        assert results[0]["last"] == 0
        assert results[1]["payload"] == 0xBB
        assert results[1]["first"] == 0
        assert results[1]["last"] == 1

    def test_unpack_backpressure(self):
        """Unpack with random backpressure."""
        o_sig = Signature(unsigned(8))
        dut = Unpack(o_sig, 4)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream, random_valid=True, seed=42)
            await sender.send(ctx, 0x04030201)
            await sender.send(ctx, 0x08070605)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=99)
            for _ in range(8):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_unpack_bp.vcd")

        assert results == [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]


# ---------------------------------------------------------------------------
# Pack/Unpack roundtrip tests
# ---------------------------------------------------------------------------

class TestPackUnpackRoundtrip:
    """Test Pack → Unpack roundtrip."""

    def test_pack_unpack_roundtrip(self):
        """Pack 4 beats, then unpack back to 4 beats."""
        from amaranth import Module
        from amaranth.lib import wiring as wiring_lib
        from amaranth.lib.wiring import In, Out, connect

        class PackUnpack(wiring_lib.Component):
            def __init__(self):
                i_sig = Signature(unsigned(8))
                o_sig = Signature(unsigned(8))
                super().__init__({
                    "i_stream": In(i_sig),
                    "o_stream": Out(o_sig),
                })

            def elaborate(self, platform):
                m = Module()
                m.submodules.pack = pack_m = Pack(Signature(unsigned(8)), 4)
                m.submodules.unpack = unpack_m = Unpack(Signature(unsigned(8)), 4)

                connect(m, wiring_lib.flipped(self.i_stream), pack_m.i_stream)
                connect(m, pack_m.o_stream, unpack_m.i_stream)
                connect(m, unpack_m.o_stream, wiring_lib.flipped(self.o_stream))
                return m

        dut = PackUnpack()
        results = []
        expected = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_pack_unpack_roundtrip.vcd")

        assert results == expected


# ---------------------------------------------------------------------------
# StrideConverter tests
# ---------------------------------------------------------------------------

class TestStrideConverter:
    """Test StrideConverter."""

    def test_stride_integer_ratio(self):
        """Integer ratio: 8→16 (same as StreamConverter)."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(16))
        dut = StrideConverter(i_sig, o_sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in [0xAB, 0xCD]:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            beat = await receiver.recv(ctx)
            results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_stride_int.vcd")

        assert results == [0xCDAB]

    def test_stride_identity(self):
        """Same width: wire-through."""
        i_sig = Signature(unsigned(8))
        o_sig = Signature(unsigned(8))
        dut = StrideConverter(i_sig, o_sig)
        results = []
        expected = [0x11, 0x22, 0x33]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_stride_identity.vcd")

        assert results == expected

    def test_stride_non_integer_ratio(self):
        """Non-integer ratio: 6→4 (LCM=12, 2 in → 3 out)."""
        i_sig = Signature(unsigned(6))
        o_sig = Signature(unsigned(4))
        dut = StrideConverter(i_sig, o_sig)
        results = []

        # 2 x 6-bit inputs = 12 bits → 3 x 4-bit outputs
        input_vals = [0b110011, 0b010101]
        combined = input_vals[0] | (input_vals[1] << 6)
        expected = []
        for i in range(3):
            expected.append((combined >> (i * 4)) & 0xF)

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in input_vals:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(3):
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, deadline_ns=200_000,
                 vcd_name="test_stride_non_int.vcd")

        assert results == expected
