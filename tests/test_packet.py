"""Tests for amaranth_stream.packet."""

import pytest

from amaranth import *
from amaranth.hdl import unsigned
from amaranth.sim import Simulator, Period

from amaranth_stream._base import Signature
from amaranth_stream.packet import (
    HeaderLayout,
    Packetizer,
    Depacketizer,
    PacketFIFO,
    PacketStatus,
    Stitcher,
    LastInserter,
    LastOnTimeout,
)
from amaranth_stream.sim import StreamSimSender, StreamSimReceiver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_sim(dut, *testbenches, deadline_ns=50_000, vcd_name="test_packet.vcd"):
    """Helper to run a simulation with one or more testbenches."""
    sim = Simulator(dut)
    sim.add_clock(Period(MHz=10))
    for tb in testbenches:
        sim.add_testbench(tb)
    with sim.write_vcd(vcd_name):
        sim.run_until(Period(ns=deadline_ns))


# ===========================================================================
# HeaderLayout tests
# ===========================================================================

class TestHeaderLayout:
    """Test HeaderLayout declarative header definition."""

    def test_header_layout_basic(self):
        """Create a simple header layout and check properties."""
        hl = HeaderLayout({"type": (8, 0)})
        assert hl.byte_length == 1
        assert "type" in hl.fields
        sl = hl.struct_layout
        # StructLayout should have the field
        assert "type" in dict(sl)

    def test_header_layout_multi_field(self):
        """Multiple fields with different offsets."""
        hl = HeaderLayout({
            "src": (8, 0),
            "dst": (8, 1),
            "length": (16, 2),
        })
        assert hl.byte_length == 4  # offset 2 + ceil(16/8) = 4
        assert hl.fields["src"] == (8, 0)
        assert hl.fields["dst"] == (8, 1)
        assert hl.fields["length"] == (16, 2)

    def test_header_layout_non_byte_aligned(self):
        """Field width not a multiple of 8."""
        hl = HeaderLayout({"flags": (3, 0)})
        assert hl.byte_length == 1  # ceil(3/8) = 1


# ===========================================================================
# Packetizer tests
# ===========================================================================

class TestPacketizer:
    """Test Packetizer — insert header beats before payload."""

    def test_packetizer_basic(self):
        """Insert a 1-byte header before a 3-beat payload (8-bit stream)."""
        hl = HeaderLayout({"type": (8, 0)})
        sig = Signature(unsigned(8), has_first_last=True)
        dut = Packetizer(hl, sig)
        results = []

        async def testbench(ctx):
            sender = StreamSimSender(dut.i_stream)
            receiver = StreamSimReceiver(dut.o_stream)

            # Set header
            ctx.set(dut.header.type, 0x42)

            # Send payload (3 beats)
            async def send_payload():
                await sender.send(ctx, 0xAA, first=1, last=0)
                await sender.send(ctx, 0xBB, first=0, last=0)
                await sender.send(ctx, 0xCC, first=0, last=1)

            async def recv_all():
                for _ in range(4):  # 1 header + 3 payload
                    beat = await receiver.recv(ctx)
                    results.append(beat)

            # Run sender and receiver concurrently by interleaving
            # We need to use separate testbenches for this
            pass

        # Use separate testbenches for sender and receiver
        results_list = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            # Set header
            ctx.set(dut.header.type, 0x42)
            # Wait a tick for header to be set
            await ctx.tick()
            # Send payload
            await sender.send(ctx, 0xAA, first=1, last=0)
            await sender.send(ctx, 0xBB, first=0, last=0)
            await sender.send(ctx, 0xCC, first=0, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(4):  # 1 header + 3 payload
                beat = await receiver.recv(ctx)
                results_list.append(beat)

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_packetizer_basic.vcd")

        assert len(results_list) == 4
        # First beat is header
        assert results_list[0]["payload"] == 0x42
        assert results_list[0]["first"] == 1
        assert results_list[0]["last"] == 0
        # Payload beats
        assert results_list[1]["payload"] == 0xAA
        assert results_list[1]["first"] == 0
        assert results_list[2]["payload"] == 0xBB
        assert results_list[2]["first"] == 0
        assert results_list[3]["payload"] == 0xCC
        assert results_list[3]["last"] == 1

    def test_packetizer_multi_beat_header(self):
        """Header larger than payload width requires multiple beats."""
        # 2-byte header on an 8-bit stream = 2 header beats
        hl = HeaderLayout({
            "src": (8, 0),
            "dst": (8, 1),
        })
        sig = Signature(unsigned(8), has_first_last=True)
        dut = Packetizer(hl, sig)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            ctx.set(dut.header.src, 0x11)
            ctx.set(dut.header.dst, 0x22)
            await ctx.tick()
            await sender.send(ctx, 0xDD, first=1, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(3):  # 2 header + 1 payload
                beat = await receiver.recv(ctx)
                results.append(beat)

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_packetizer_multi_beat.vcd")

        assert len(results) == 3
        # First header beat (byte 0 = src)
        assert results[0]["payload"] == 0x11
        assert results[0]["first"] == 1
        # Second header beat (byte 1 = dst)
        assert results[1]["payload"] == 0x22
        assert results[1]["first"] == 0
        # Payload
        assert results[2]["payload"] == 0xDD
        assert results[2]["last"] == 1


# ===========================================================================
# Depacketizer tests
# ===========================================================================

class TestDepacketizer:
    """Test Depacketizer — extract header from packet start."""

    def test_depacketizer_basic(self):
        """Extract 1-byte header, pass through payload."""
        hl = HeaderLayout({"type": (8, 0)})
        sig = Signature(unsigned(8), has_first_last=True)
        dut = Depacketizer(hl, sig)
        results = []
        header_val = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            # Send header beat
            await sender.send(ctx, 0x42, first=1, last=0)
            # Send payload beats
            await sender.send(ctx, 0xAA, first=0, last=0)
            await sender.send(ctx, 0xBB, first=0, last=0)
            await sender.send(ctx, 0xCC, first=0, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(3):  # 3 payload beats (header stripped)
                beat = await receiver.recv(ctx)
                results.append(beat)
            # Read header output
            await ctx.tick()
            header_val.append(ctx.get(dut.header.type))

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_depacketizer_basic.vcd")

        assert len(results) == 3
        assert results[0]["payload"] == 0xAA
        assert results[0]["first"] == 1  # First payload beat after header
        assert results[1]["payload"] == 0xBB
        assert results[1]["first"] == 0
        assert results[2]["payload"] == 0xCC
        assert results[2]["last"] == 1
        assert header_val[0] == 0x42

    def test_depacketizer_multi_beat_header(self):
        """Multi-beat header extraction."""
        hl = HeaderLayout({
            "src": (8, 0),
            "dst": (8, 1),
        })
        sig = Signature(unsigned(8), has_first_last=True)
        dut = Depacketizer(hl, sig)
        results = []
        header_vals = {}

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            # Send 2 header beats
            await sender.send(ctx, 0x11, first=1, last=0)
            await sender.send(ctx, 0x22, first=0, last=0)
            # Send payload
            await sender.send(ctx, 0xDD, first=0, last=1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            beat = await receiver.recv(ctx)
            results.append(beat)
            # Read header
            await ctx.tick()
            header_vals["src"] = ctx.get(dut.header.src)
            header_vals["dst"] = ctx.get(dut.header.dst)

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_depacketizer_multi_beat.vcd")

        assert len(results) == 1
        assert results[0]["payload"] == 0xDD
        assert results[0]["first"] == 1
        assert results[0]["last"] == 1
        assert header_vals["src"] == 0x11
        assert header_vals["dst"] == 0x22


# ===========================================================================
# PacketFIFO tests
# ===========================================================================

class TestPacketFIFO:
    """Test PacketFIFO — atomic packet FIFO."""

    def test_packet_fifo_basic(self):
        """Write and read a complete packet."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = PacketFIFO(sig, payload_depth=16, packet_depth=4)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send_packet(ctx, [0x10, 0x20, 0x30])

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            # Wait for packet to be committed
            for _ in range(10):
                await ctx.tick()
            packet = await receiver.recv_packet(ctx)
            results.extend(packet)

        _run_sim(dut, sender_tb, receiver_tb,
                 deadline_ns=100_000, vcd_name="test_pkt_fifo_basic.vcd")

        assert len(results) == 3
        assert results[0]["payload"] == 0x10
        assert results[0]["first"] == 1
        assert results[1]["payload"] == 0x20
        assert results[2]["payload"] == 0x30
        assert results[2]["last"] == 1

    def test_packet_fifo_multiple_packets(self):
        """Multiple packets buffered and read back."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = PacketFIFO(sig, payload_depth=32, packet_depth=4)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send_packet(ctx, [0x01, 0x02])
            await sender.send_packet(ctx, [0x03, 0x04, 0x05])

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            # Wait for packets to be committed
            for _ in range(15):
                await ctx.tick()
            pkt1 = await receiver.recv_packet(ctx)
            results.append(pkt1)
            pkt2 = await receiver.recv_packet(ctx)
            results.append(pkt2)

        _run_sim(dut, sender_tb, receiver_tb,
                 deadline_ns=200_000, vcd_name="test_pkt_fifo_multi.vcd")

        assert len(results) == 2
        assert len(results[0]) == 2
        assert results[0][0]["payload"] == 0x01
        assert results[0][1]["payload"] == 0x02
        assert len(results[1]) == 3
        assert results[1][0]["payload"] == 0x03
        assert results[1][2]["payload"] == 0x05

    def test_packet_fifo_backpressure(self):
        """Backpressure handling — receiver delays."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = PacketFIFO(sig, payload_depth=16, packet_depth=4)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send_packet(ctx, [0xAA, 0xBB])
            await sender.send_packet(ctx, [0xCC, 0xDD])

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=42)
            # Wait for packets
            for _ in range(15):
                await ctx.tick()
            pkt1 = await receiver.recv_packet(ctx)
            results.append(pkt1)
            pkt2 = await receiver.recv_packet(ctx)
            results.append(pkt2)

        _run_sim(dut, sender_tb, receiver_tb,
                 deadline_ns=200_000, vcd_name="test_pkt_fifo_bp.vcd")

        assert len(results) == 2
        assert results[0][0]["payload"] == 0xAA
        assert results[0][1]["payload"] == 0xBB
        assert results[1][0]["payload"] == 0xCC
        assert results[1][1]["payload"] == 0xDD


# ===========================================================================
# PacketStatus tests
# ===========================================================================

class TestPacketStatus:
    """Test PacketStatus — packet boundary tracker."""

    def test_packet_status_basic(self):
        """in_packet tracks packet boundaries."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = PacketStatus(sig)
        in_packet_values = []

        async def testbench(ctx):
            # Initially not in packet
            await ctx.tick()
            in_packet_values.append(ctx.get(dut.in_packet))

            # Simulate a transfer with first=1
            ctx.set(dut.stream.valid, 1)
            ctx.set(dut.stream.ready, 1)
            ctx.set(dut.stream.first, 1)
            ctx.set(dut.stream.last, 0)
            ctx.set(dut.stream.payload, 0xAA)
            await ctx.tick()

            # After first, should be in packet
            ctx.set(dut.stream.first, 0)
            await ctx.tick()
            in_packet_values.append(ctx.get(dut.in_packet))

            # Middle beat
            ctx.set(dut.stream.payload, 0xBB)
            await ctx.tick()
            in_packet_values.append(ctx.get(dut.in_packet))

            # Last beat
            ctx.set(dut.stream.last, 1)
            ctx.set(dut.stream.payload, 0xCC)
            await ctx.tick()

            # After last, should not be in packet
            ctx.set(dut.stream.valid, 0)
            ctx.set(dut.stream.last, 0)
            await ctx.tick()
            in_packet_values.append(ctx.get(dut.in_packet))

        _run_sim(dut, testbench, vcd_name="test_pkt_status.vcd")

        assert in_packet_values[0] == 0  # Before packet
        assert in_packet_values[1] == 1  # In packet
        assert in_packet_values[2] == 1  # Still in packet
        assert in_packet_values[3] == 0  # After packet


# ===========================================================================
# Stitcher tests
# ===========================================================================

class TestStitcher:
    """Test Stitcher — group N consecutive packets into one."""

    def test_stitcher_basic(self):
        """Stitch 2 packets into 1."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = Stitcher(sig, n=2)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            # Packet 1: [0x01, 0x02]
            await sender.send_packet(ctx, [0x01, 0x02])
            # Packet 2: [0x03, 0x04]
            await sender.send_packet(ctx, [0x03, 0x04])

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            # Should receive one stitched packet of 4 beats
            packet = await receiver.recv_packet(ctx)
            results.extend(packet)

        _run_sim(dut, sender_tb, receiver_tb,
                 deadline_ns=100_000, vcd_name="test_stitcher_2.vcd")

        assert len(results) == 4
        assert results[0]["payload"] == 0x01
        assert results[0]["first"] == 1
        assert results[0]["last"] == 0
        assert results[1]["payload"] == 0x02
        assert results[1]["first"] == 0
        assert results[1]["last"] == 0  # Suppressed
        assert results[2]["payload"] == 0x03
        assert results[2]["first"] == 0  # Suppressed
        assert results[2]["last"] == 0
        assert results[3]["payload"] == 0x04
        assert results[3]["first"] == 0
        assert results[3]["last"] == 1

    def test_stitcher_3(self):
        """Stitch 3 packets into 1."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = Stitcher(sig, n=3)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send_packet(ctx, [0x10])
            await sender.send_packet(ctx, [0x20])
            await sender.send_packet(ctx, [0x30])

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            packet = await receiver.recv_packet(ctx)
            results.extend(packet)

        _run_sim(dut, sender_tb, receiver_tb,
                 deadline_ns=100_000, vcd_name="test_stitcher_3.vcd")

        assert len(results) == 3
        assert results[0]["payload"] == 0x10
        assert results[0]["first"] == 1
        assert results[0]["last"] == 0
        assert results[1]["payload"] == 0x20
        assert results[1]["first"] == 0
        assert results[1]["last"] == 0
        assert results[2]["payload"] == 0x30
        assert results[2]["first"] == 0
        assert results[2]["last"] == 1


# ===========================================================================
# LastInserter tests
# ===========================================================================

class TestLastInserter:
    """Test LastInserter — inject last=1 every N beats."""

    def test_last_inserter_basic(self):
        """Insert last every 4 beats."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = LastInserter(sig, n=4)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for i in range(8):
                await sender.send(ctx, i)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(8):
                beat = await receiver.recv(ctx)
                results.append(beat)

        _run_sim(dut, sender_tb, receiver_tb,
                 deadline_ns=100_000, vcd_name="test_last_inserter_4.vcd")

        assert len(results) == 8
        # Beat 0: first=1, last=0
        assert results[0]["first"] == 1
        assert results[0]["last"] == 0
        # Beat 3: first=0, last=1
        assert results[3]["first"] == 0
        assert results[3]["last"] == 1
        # Beat 4: first=1, last=0 (new packet)
        assert results[4]["first"] == 1
        assert results[4]["last"] == 0
        # Beat 7: first=0, last=1
        assert results[7]["first"] == 0
        assert results[7]["last"] == 1

    def test_last_inserter_with_first(self):
        """First/last framing with n=2."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = LastInserter(sig, n=2)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for i in range(4):
                await sender.send(ctx, i + 1)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in range(4):
                beat = await receiver.recv(ctx)
                results.append(beat)

        _run_sim(dut, sender_tb, receiver_tb,
                 deadline_ns=100_000, vcd_name="test_last_inserter_fl.vcd")

        assert len(results) == 4
        # Packet 1: beats 0,1
        assert results[0]["first"] == 1
        assert results[0]["last"] == 0
        assert results[0]["payload"] == 1
        assert results[1]["first"] == 0
        assert results[1]["last"] == 1
        assert results[1]["payload"] == 2
        # Packet 2: beats 2,3
        assert results[2]["first"] == 1
        assert results[2]["last"] == 0
        assert results[2]["payload"] == 3
        assert results[3]["first"] == 0
        assert results[3]["last"] == 1
        assert results[3]["payload"] == 4


# ===========================================================================
# LastOnTimeout tests
# ===========================================================================

class TestLastOnTimeout:
    """Test LastOnTimeout — inject last=1 after idle timeout."""

    def test_last_on_timeout_basic(self):
        """Timeout triggers last after idle cycles."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = LastOnTimeout(sig, timeout=3)
        results = []

        async def testbench(ctx):
            # Send first beat with first=1
            ctx.set(dut.i_stream.payload, 0xAA)
            ctx.set(dut.i_stream.valid, 1)
            ctx.set(dut.i_stream.first, 1)
            ctx.set(dut.i_stream.last, 0)
            ctx.set(dut.o_stream.ready, 1)
            await ctx.tick()

            # Deassert valid (idle)
            ctx.set(dut.i_stream.valid, 0)
            ctx.set(dut.i_stream.first, 0)

            # Wait for timeout (3 idle cycles)
            for _ in range(4):
                await ctx.tick()

            # Now send another beat — should have force_last
            ctx.set(dut.i_stream.payload, 0xBB)
            ctx.set(dut.i_stream.valid, 1)
            ctx.set(dut.i_stream.last, 0)

            # Sample output
            _, _, last_val = await ctx.tick().sample(dut.o_stream.last)
            results.append(last_val)

        _run_sim(dut, testbench, vcd_name="test_last_timeout.vcd")

        # The beat after timeout should have last=1
        assert results[0] == 1

    def test_last_on_timeout_no_timeout(self):
        """Normal last passes through without timeout interference."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = LastOnTimeout(sig, timeout=10)
        results = []

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            await sender.send_packet(ctx, [0x01, 0x02, 0x03])

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            packet = await receiver.recv_packet(ctx)
            results.extend(packet)

        _run_sim(dut, sender_tb, receiver_tb,
                 vcd_name="test_last_no_timeout.vcd")

        assert len(results) == 3
        assert results[0]["payload"] == 0x01
        assert results[0]["first"] == 1
        assert results[2]["payload"] == 0x03
        assert results[2]["last"] == 1
