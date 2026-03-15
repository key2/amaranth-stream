"""Tests for amaranth_stream.monitor (StreamMonitor, StreamChecker)."""

import pytest

from amaranth import *
from amaranth.hdl import unsigned, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out, connect
from amaranth.sim import Simulator, Period

from amaranth_stream._base import Signature
from amaranth_stream.monitor import StreamMonitor, StreamChecker
from amaranth_stream.sim import StreamSimSender, StreamSimReceiver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_sim(dut, *testbenches, deadline_ns=50_000, vcd_name="test_monitor.vcd"):
    """Helper to run a simulation with one or more testbenches."""
    sim = Simulator(dut)
    sim.add_clock(Period(MHz=10))
    for tb in testbenches:
        sim.add_testbench(tb)
    with sim.write_vcd(vcd_name):
        sim.run_until(Period(ns=deadline_ns))


# ---------------------------------------------------------------------------
# StreamMonitor tests
# ---------------------------------------------------------------------------

class TestStreamMonitor:
    """Test StreamMonitor (performance counters)."""

    def test_monitor_transfer_count(self):
        """Count completed transfers."""
        sig = Signature(unsigned(8))
        dut = StreamMonitor(sig)
        transfer_count = []

        async def tb(ctx):
            # Send 5 beats
            for i in range(5):
                ctx.set(dut.i_stream.payload, i)
                ctx.set(dut.i_stream.valid, 1)
                ctx.set(dut.o_stream.ready, 1)
                await ctx.tick()

            # Deassert before waiting for counter to update
            ctx.set(dut.i_stream.valid, 0)
            ctx.set(dut.o_stream.ready, 0)
            await ctx.tick()
            transfer_count.append(ctx.get(dut.transfer_count))

        _run_sim(dut, tb, vcd_name="test_mon_transfer.vcd")
        assert transfer_count[0] == 5

    def test_monitor_stall_count(self):
        """Count stall cycles (valid & ~ready)."""
        sig = Signature(unsigned(8))
        dut = StreamMonitor(sig)
        stall_count = []

        async def tb(ctx):
            # Create 3 stall cycles: valid=1, ready=0
            for _ in range(3):
                ctx.set(dut.i_stream.valid, 1)
                ctx.set(dut.o_stream.ready, 0)
                await ctx.tick()

            # Then do a transfer to end the stall
            ctx.set(dut.i_stream.valid, 1)
            ctx.set(dut.o_stream.ready, 1)
            await ctx.tick()

            # Wait for counter to update
            ctx.set(dut.i_stream.valid, 0)
            await ctx.tick()
            stall_count.append(ctx.get(dut.stall_count))

        _run_sim(dut, tb, vcd_name="test_mon_stall.vcd")
        assert stall_count[0] == 3

    def test_monitor_idle_count(self):
        """Count idle cycles (~valid & ready)."""
        sig = Signature(unsigned(8))
        dut = StreamMonitor(sig)
        idle_count = []

        async def tb(ctx):
            # Create 4 idle cycles: valid=0, ready=1
            for _ in range(4):
                ctx.set(dut.i_stream.valid, 0)
                ctx.set(dut.o_stream.ready, 1)
                await ctx.tick()

            # Wait for counter to update
            ctx.set(dut.o_stream.ready, 0)
            await ctx.tick()
            idle_count.append(ctx.get(dut.idle_count))

        _run_sim(dut, tb, vcd_name="test_mon_idle.vcd")
        assert idle_count[0] == 4

    def test_monitor_packet_count(self):
        """Count completed packets (valid & ready & last)."""
        sig = Signature(unsigned(8), has_first_last=True)
        dut = StreamMonitor(sig)
        packet_count = []

        async def tb(ctx):
            # Send 2 packets: [A, B, C(last)], [D, E(last)]
            for val, last in [(0xA, 0), (0xB, 0), (0xC, 1), (0xD, 0), (0xE, 1)]:
                ctx.set(dut.i_stream.payload, val)
                ctx.set(dut.i_stream.valid, 1)
                ctx.set(dut.i_stream.last, last)
                ctx.set(dut.o_stream.ready, 1)
                await ctx.tick()

            ctx.set(dut.i_stream.valid, 0)
            await ctx.tick()
            packet_count.append(ctx.get(dut.packet_count))

        _run_sim(dut, tb, vcd_name="test_mon_packet.vcd")
        assert packet_count[0] == 2

    def test_monitor_clear(self):
        """Clear resets all counters to 0."""
        sig = Signature(unsigned(8))
        dut = StreamMonitor(sig)
        counts_after_clear = []

        async def tb(ctx):
            # Generate some transfers
            for _ in range(3):
                ctx.set(dut.i_stream.valid, 1)
                ctx.set(dut.o_stream.ready, 1)
                await ctx.tick()

            # Wait for counters to update
            ctx.set(dut.i_stream.valid, 0)
            ctx.set(dut.o_stream.ready, 0)
            await ctx.tick()

            # Assert clear
            ctx.set(dut.clear, 1)
            await ctx.tick()
            ctx.set(dut.clear, 0)
            await ctx.tick()

            counts_after_clear.append(ctx.get(dut.transfer_count))
            counts_after_clear.append(ctx.get(dut.stall_count))
            counts_after_clear.append(ctx.get(dut.idle_count))

        _run_sim(dut, tb, vcd_name="test_mon_clear.vcd")
        assert counts_after_clear == [0, 0, 0]

    def test_monitor_passthrough(self):
        """Data passes through monitor unchanged."""
        sig = Signature(unsigned(8))
        dut = StreamMonitor(sig)
        results = []
        expected = [0xAA, 0xBB, 0xCC]

        async def sender_tb(ctx):
            sender = StreamSimSender(dut.i_stream)
            for val in expected:
                await sender.send(ctx, val)

        async def receiver_tb(ctx):
            receiver = StreamSimReceiver(dut.o_stream)
            for _ in expected:
                beat = await receiver.recv(ctx)
                results.append(beat["payload"])

        _run_sim(dut, sender_tb, receiver_tb, vcd_name="test_mon_passthrough.vcd")
        assert results == expected


# ---------------------------------------------------------------------------
# StreamChecker tests
# ---------------------------------------------------------------------------

class _CheckerTestHarness(wiring.Component):
    """Test harness that wraps a StreamChecker with a driveable stream."""

    def __init__(self, signature):
        self._stream_sig = signature
        super().__init__({
            "stream": Out(signature),
            "error": Out(1),
        })
        self._checker = StreamChecker(signature)

    def elaborate(self, platform):
        m = Module()
        m.submodules.checker = checker = self._checker

        # Connect our stream output to checker's stream input
        m.d.comb += [
            checker.stream.payload.eq(self.stream.payload),
            checker.stream.valid.eq(self.stream.valid),
            checker.stream.ready.eq(self.stream.ready),
        ]
        if self._stream_sig.has_first_last:
            m.d.comb += [
                checker.stream.first.eq(self.stream.first),
                checker.stream.last.eq(self.stream.last),
            ]
        m.d.comb += self.error.eq(checker.error)

        return m


class TestStreamChecker:
    """Test StreamChecker (protocol assertion checker)."""

    def test_checker_valid_stability(self):
        """Detect valid deassert violation (valid drops without transfer)."""
        sig = Signature(unsigned(8))
        dut = _CheckerTestHarness(sig)
        error_detected = []

        async def tb(ctx):
            # Assert valid with payload
            ctx.set(dut.stream.payload, 0x42)
            ctx.set(dut.stream.valid, 1)
            ctx.set(dut.stream.ready, 0)  # no transfer
            await ctx.tick()

            # Deassert valid without transfer — violation!
            ctx.set(dut.stream.valid, 0)
            await ctx.tick()

            # Wait for error to propagate
            await ctx.tick()
            error_detected.append(ctx.get(dut.error))

        _run_sim(dut, tb, vcd_name="test_checker_valid.vcd")
        assert error_detected[0] == 1

    def test_checker_payload_stability(self):
        """Detect payload change violation (payload changes while valid & ~ready)."""
        sig = Signature(unsigned(8))
        dut = _CheckerTestHarness(sig)
        error_detected = []

        async def tb(ctx):
            # Assert valid with payload
            ctx.set(dut.stream.payload, 0x42)
            ctx.set(dut.stream.valid, 1)
            ctx.set(dut.stream.ready, 0)  # no transfer
            await ctx.tick()

            # Change payload without transfer — violation!
            ctx.set(dut.stream.payload, 0x99)
            ctx.set(dut.stream.valid, 1)
            ctx.set(dut.stream.ready, 0)
            await ctx.tick()

            # Wait for error to propagate
            await ctx.tick()
            error_detected.append(ctx.get(dut.error))

        _run_sim(dut, tb, vcd_name="test_checker_payload.vcd")
        assert error_detected[0] == 1

    def test_checker_no_error(self):
        """No error on correct protocol usage."""
        sig = Signature(unsigned(8))
        dut = _CheckerTestHarness(sig)
        error_detected = []

        async def tb(ctx):
            # Correct: assert valid, then transfer happens
            ctx.set(dut.stream.payload, 0x42)
            ctx.set(dut.stream.valid, 1)
            ctx.set(dut.stream.ready, 1)  # transfer happens
            await ctx.tick()

            # Next beat
            ctx.set(dut.stream.payload, 0x99)
            ctx.set(dut.stream.valid, 1)
            ctx.set(dut.stream.ready, 1)
            await ctx.tick()

            # Deassert valid after transfer (OK)
            ctx.set(dut.stream.valid, 0)
            await ctx.tick()

            await ctx.tick()
            error_detected.append(ctx.get(dut.error))

        _run_sim(dut, tb, vcd_name="test_checker_ok.vcd")
        assert error_detected[0] == 0
