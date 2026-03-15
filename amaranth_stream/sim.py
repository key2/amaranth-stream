"""Simulation Bus Functional Models (BFMs) for amaranth-stream.

Provides :class:`StreamSimSender` and :class:`StreamSimReceiver` for driving
and consuming streams in Amaranth async testbenches.

Usage example::

    async def testbench(ctx):
        sender = StreamSimSender(dut.i_stream)
        receiver = StreamSimReceiver(dut.o_stream)

        await sender.send(ctx, 0xAB)
        beat = await receiver.recv(ctx)
        assert beat["payload"] == 0xAB

These BFMs use ``ctx.tick().sample()`` to capture signal values at the exact
clock edge, avoiding race conditions between concurrent testbenches.
"""

import random

__all__ = ["StreamSimSender", "StreamSimReceiver"]


class StreamSimSender:
    """Simulation BFM that drives a stream source (initiator side).

    In a testbench, call :meth:`send` to push a single beat or
    :meth:`send_packet` to push a sequence of beats with automatic
    ``first``/``last`` framing.

    Parameters
    ----------
    stream : stream :class:`Interface`
        The stream interface to drive. The sender drives ``payload``,
        ``valid``, and optionally ``first``, ``last``, ``param``, ``keep``.
    domain : :class:`str`
        Clock domain name (default ``"sync"``).
    random_valid : :class:`bool`
        If ``True``, randomly deassert ``valid`` to stress-test backpressure.
    seed : :class:`int` or ``None``
        RNG seed for reproducible random delays.
    """

    def __init__(self, stream, *, domain="sync", random_valid=False, seed=None):
        self._stream = stream
        self._domain = domain
        self._random_valid = random_valid
        self._rng = random.Random(seed)

    async def send(self, ctx, payload, *, first=None, last=None, param=None, keep=None):
        """Send a single beat on the stream.

        Drives ``payload`` and ``valid``, waits for the handshake (``valid``
        AND ``ready`` both high on a clock edge), then deasserts ``valid``.

        Parameters
        ----------
        ctx : testbench context
            The ``ctx`` argument from an ``async def testbench(ctx)`` function.
        payload : :class:`int`
            Payload value to send.
        first : :class:`int` or ``None``
            Value for the ``first`` signal (if the stream has one).
        last : :class:`int` or ``None``
            Value for the ``last`` signal (if the stream has one).
        param : :class:`int` or ``None``
            Value for the ``param`` signal (if the stream has one).
        keep : :class:`int` or ``None``
            Value for the ``keep`` signal (if the stream has one).
        """
        stream = self._stream

        # Random back-off: deassert valid for a random number of cycles
        if self._random_valid:
            while self._rng.random() < 0.3:
                ctx.set(stream.valid, 0)
                await ctx.tick(self._domain)

        # Drive payload and sideband signals
        ctx.set(stream.payload, payload)
        ctx.set(stream.valid, 1)

        if first is not None and hasattr(stream, "first"):
            ctx.set(stream.first, first)
        if last is not None and hasattr(stream, "last"):
            ctx.set(stream.last, last)
        if param is not None and hasattr(stream, "param"):
            ctx.set(stream.param, param)
        if keep is not None and hasattr(stream, "keep"):
            ctx.set(stream.keep, keep)

        # Wait for handshake: sample ready at the clock edge
        while True:
            _, _, ready_val = await ctx.tick(self._domain).sample(stream.ready)
            if ready_val:
                break

        # Deassert valid after the transfer
        ctx.set(stream.valid, 0)

    async def send_packet(self, ctx, payloads, *, param=None):
        """Send a complete packet with automatic ``first``/``last`` framing.

        Parameters
        ----------
        ctx : testbench context
        payloads : iterable of :class:`int`
            Sequence of payload values forming the packet.
        param : :class:`int` or ``None``
            Constant ``param`` value for every beat.
        """
        payloads = list(payloads)
        for i, payload in enumerate(payloads):
            is_first = 1 if i == 0 else 0
            is_last = 1 if i == len(payloads) - 1 else 0
            await self.send(ctx, payload, first=is_first, last=is_last, param=param)


class StreamSimReceiver:
    """Simulation BFM that consumes a stream sink (responder side).

    In a testbench, call :meth:`recv` to receive a single beat or
    :meth:`recv_packet` to receive beats until ``last=1``.

    Parameters
    ----------
    stream : stream :class:`Interface`
        The stream interface to consume. The receiver drives ``ready``
        and reads ``payload``, ``valid``, and optionally ``first``,
        ``last``, ``param``, ``keep``.
    domain : :class:`str`
        Clock domain name (default ``"sync"``).
    random_ready : :class:`bool`
        If ``True``, randomly deassert ``ready`` to stress-test flow control.
    seed : :class:`int` or ``None``
        RNG seed for reproducible random delays.
    """

    def __init__(self, stream, *, domain="sync", random_ready=False, seed=None):
        self._stream = stream
        self._domain = domain
        self._random_ready = random_ready
        self._rng = random.Random(seed)

    async def recv(self, ctx):
        """Receive a single beat from the stream.

        Asserts ``ready``, waits for the handshake (``valid`` AND ``ready``
        both high on a clock edge), captures the data, then deasserts ``ready``.

        Returns
        -------
        :class:`dict`
            Dictionary with ``"payload"`` and optionally ``"first"``,
            ``"last"``, ``"param"``, ``"keep"`` keys.
        """
        stream = self._stream

        # Random back-off: deassert ready for a random number of cycles
        if self._random_ready:
            while self._rng.random() < 0.3:
                ctx.set(stream.ready, 0)
                await ctx.tick(self._domain)

        # Assert ready
        ctx.set(stream.ready, 1)

        # Build the list of signals to sample at the clock edge
        sample_signals = [stream.valid, stream.payload]
        has_first = hasattr(stream, "first")
        has_last = hasattr(stream, "last")
        has_param = hasattr(stream, "param")
        has_keep = hasattr(stream, "keep")
        if has_first:
            sample_signals.append(stream.first)
        if has_last:
            sample_signals.append(stream.last)
        if has_param:
            sample_signals.append(stream.param)
        if has_keep:
            sample_signals.append(stream.keep)

        # Wait for handshake: sample valid and data at the clock edge
        while True:
            _, _, *sampled = await ctx.tick(self._domain).sample(*sample_signals)
            valid_val = sampled[0]
            if valid_val:
                break

        # Extract captured data from sampled values
        payload_val = sampled[1]
        result = {"payload": payload_val}
        idx = 2
        if has_first:
            result["first"] = sampled[idx]
            idx += 1
        if has_last:
            result["last"] = sampled[idx]
            idx += 1
        if has_param:
            result["param"] = sampled[idx]
            idx += 1
        if has_keep:
            result["keep"] = sampled[idx]
            idx += 1

        # Deassert ready after the transfer
        ctx.set(stream.ready, 0)

        return result

    async def recv_packet(self, ctx):
        """Receive beats until ``last=1``.

        Returns
        -------
        :class:`list` of :class:`dict`
            List of beat dictionaries (see :meth:`recv`).
        """
        beats = []
        while True:
            beat = await self.recv(ctx)
            beats.append(beat)
            # If no 'last' field, treat as single-beat packet
            if beat.get("last", 1):
                break
        return beats

    async def expect_packet(self, ctx, expected_payloads):
        """Receive a packet and assert payloads match.

        Parameters
        ----------
        ctx : testbench context
        expected_payloads : iterable of :class:`int`
            Expected payload values.

        Raises
        ------
        :exc:`AssertionError`
            If the number of beats or any payload value doesn't match.
        """
        expected_payloads = list(expected_payloads)
        beats = await self.recv_packet(ctx)
        assert len(beats) == len(expected_payloads), \
            f"Expected {len(expected_payloads)} beats, got {len(beats)}"
        for i, (beat, expected) in enumerate(zip(beats, expected_payloads)):
            assert beat["payload"] == expected, \
                f"Beat {i}: expected payload {expected:#x}, got {beat['payload']:#x}"
