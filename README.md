# amaranth-stream

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Amaranth HDL](https://img.shields.io/badge/Amaranth-HDL-blueviolet.svg)](https://amaranth-lang.org/)
[![License: BSD-2](https://img.shields.io/badge/license-BSD--2-green.svg)](LICENSE.txt)
[![PDM](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm-project.org)

**A comprehensive stream processing library for [Amaranth HDL](https://amaranth-lang.org/)** — providing 52 production-ready components for building high-performance streaming data pipelines in digital hardware.

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [1. Creating a Stream Signature](#1-creating-a-stream-signature)
  - [2. Using a Buffer Pipeline Stage](#2-using-a-buffer-pipeline-stage)
  - [3. Simulation with BFMs](#3-simulation-with-bfms)
- [Stream Protocol](#stream-protocol)
  - [Valid/Ready Handshake](#validready-handshake)
  - [Optional Signals](#optional-signals)
  - [Transfer Rules](#transfer-rules)
- [API Reference](#api-reference)
  - [Core — Signature & Interface](#core--signature--interface)
    - [Signature](#signature)
    - [Interface](#interface)
    - [core_to_extended](#core_to_extended)
    - [connect_streams](#connect_streams)
  - [Simulation BFMs](#simulation-bfms)
    - [StreamSimSender](#streamsimsender)
    - [StreamSimReceiver](#streamsimreceiver)
  - [Buffering & Pipeline](#buffering--pipeline)
    - [Buffer](#buffer)
    - [PipeValid](#pipevalid)
    - [PipeReady](#pipeready)
    - [Delay](#delay)
    - [Pipeline](#pipeline)
    - [BufferizeEndpoints](#bufferizeendpoints)
  - [FIFOs & CDC](#fifos--cdc)
    - [StreamFIFO](#streamfifo)
    - [StreamAsyncFIFO](#streamasyncfifo)
    - [StreamCDC](#streamcdc)
  - [Width Conversion](#width-conversion)
    - [StreamConverter](#streamconverter)
    - [StrideConverter](#strideconverter)
    - [Gearbox](#gearbox)
    - [StreamCast](#streamcast)
    - [Pack](#pack)
    - [Unpack](#unpack)
    - [ByteEnableSerializer](#byteenableserializer)
  - [Routing](#routing)
    - [StreamMux](#streammux)
    - [StreamDemux](#streamdemux)
    - [StreamGate](#streamgate)
    - [StreamSplitter](#streamsplitter)
    - [StreamJoiner](#streamjoiner)
  - [Packet Processing](#packet-processing)
    - [HeaderLayout](#headerlayout)
    - [Packetizer](#packetizer)
    - [Depacketizer](#depacketizer)
    - [PacketFIFO](#packetfifo)
    - [PacketStatus](#packetstatus)
    - [Stitcher](#stitcher)
    - [LastInserter](#lastinserter)
    - [LastOnTimeout](#lastontimeout)
  - [Arbitration](#arbitration)
    - [StreamArbiter](#streamarbiter)
    - [StreamDispatcher](#streamdispatcher)
  - [Data Transformation](#data-transformation)
    - [StreamMap](#streammap)
    - [StreamFilter](#streamfilter)
    - [EndianSwap](#endianswap)
    - [GranularEndianSwap](#granularendianswap)
    - [ByteAligner](#bytealigner)
    - [PacketAligner](#packetaligner)
    - [WordReorder](#wordreorder)
  - [Monitoring & Debug](#monitoring--debug)
    - [StreamMonitor](#streammonitor)
    - [StreamChecker](#streamchecker)
    - [StreamProtocolChecker](#streamprotocolchecker)
  - [AXI-Stream Bridge](#axi-stream-bridge)
    - [AXIStreamSignature](#axistreamSignature)
    - [AXIStreamToStream](#axistreamtostream)
    - [StreamToAXIStream](#streamtoaxistream)
  - [SOP/EOP Adapter](#sopeop-adapter)
    - [SOPEOPAdapter](#sopeopadapter)
    - [StreamToSOPEOP](#streamtosopeop)
- [Testing](#testing)
- [Architecture Notes](#architecture-notes)
- [Component Summary Table](#component-summary-table)

---

## Overview

`amaranth-stream` extends Amaranth HDL's built-in `amaranth.lib.stream` with a richer set of stream processing primitives. The core Amaranth stream signature is `@final` and cannot be subclassed, so this library implements a parallel `Signature` / `Interface` hierarchy that adds optional `first`, `last`, `param`, and `keep` members — enabling packet framing, sideband parameters, and byte-enable masks.

### Key Features

- **Extended stream protocol** — `first`/`last` packet framing, `param` sideband, `keep` byte-enables
- **52 production-ready components** across 12 categories
- **Simulation BFMs** — `StreamSimSender` / `StreamSimReceiver` for async testbenches
- **Pipeline construction** — declarative `Pipeline` builder and `BufferizeEndpoints` wrapper
- **Width conversion** — integer-ratio, non-integer (LCM), gearbox, pack/unpack, byte-enable serialization
- **Packet processing** — packetizer, depacketizer, atomic packet FIFO, stitcher
- **Arbitration** — packet-aware round-robin/priority arbiter and dispatcher
- **AXI-Stream bridge** — bidirectional conversion to/from AXI-Stream
- **SOP/EOP adapter** — bridge to/from SOP/EOP framing (Gowin PCIe, Avalon-ST, Aurora)
- **Monitoring** — performance counters, protocol assertion checkers, protocol violation detector
- **Full test coverage** — 15 test modules with comprehensive simulation tests

### Component Categories

| Category | Components | Count |
|----------|-----------|-------|
| Core | `Signature`, `Interface`, `core_to_extended`, `connect_streams` | 4 |
| Simulation BFMs | `StreamSimSender`, `StreamSimReceiver` | 2 |
| Buffering & Pipeline | `Buffer`, `PipeValid`, `PipeReady`, `Delay`, `Pipeline`, `BufferizeEndpoints` | 6 |
| FIFOs & CDC | `StreamFIFO`, `StreamAsyncFIFO`, `StreamCDC` | 3 |
| Width Conversion | `StreamConverter`, `StrideConverter`, `Gearbox`, `StreamCast`, `Pack`, `Unpack`, `ByteEnableSerializer` | 7 |
| Routing | `StreamMux`, `StreamDemux`, `StreamGate`, `StreamSplitter`, `StreamJoiner` | 5 |
| Packet Processing | `HeaderLayout`, `Packetizer`, `Depacketizer`, `PacketFIFO`, `PacketStatus`, `Stitcher`, `LastInserter`, `LastOnTimeout` | 8 |
| Arbitration | `StreamArbiter`, `StreamDispatcher` | 2 |
| Data Transformation | `StreamMap`, `StreamFilter`, `EndianSwap`, `GranularEndianSwap`, `ByteAligner`, `PacketAligner`, `WordReorder` | 7 |
| Monitoring & Debug | `StreamMonitor`, `StreamChecker`, `StreamProtocolChecker` | 3 |
| AXI-Stream Bridge | `AXIStreamSignature`, `AXIStreamToStream`, `StreamToAXIStream` | 3 |
| SOP/EOP Adapter | `SOPEOPAdapter`, `StreamToSOPEOP` | 2 |
| **Total** | | **52** |

---

## Installation

This project uses [PDM](https://pdm-project.org) for dependency management.

```bash
# Clone the repository
git clone https://github.com/key2/amaranth-stream.git
cd amaranth-stream

# Install with PDM (creates virtualenv automatically)
pdm install

# Or install in development mode
pdm install -d
```

### Dependencies

- **Python** ≥ 3.9
- **Amaranth HDL** (installed as editable dependency from sibling directory)
- **pytest** ≥ 9.0.2 (dev dependency)

The `pyproject.toml` references Amaranth as a local editable install:

```toml
[tool.pdm.dev-dependencies]
dev = [
    "pytest>=9.0.2",
    "-e file:///${PROJECT_ROOT}/../amaranth#egg=amaranth",
]
```

---

## Quick Start

### 1. Creating a Stream Signature

```python
from amaranth_stream import Signature, Interface

# Basic 8-bit stream (valid + ready + payload)
sig = Signature(8)
stream = sig.create()
print(stream.payload)  # Signal(8)
print(stream.valid)    # Signal(1)
print(stream.ready)    # Signal(1)

# Stream with packet framing (first/last)
pkt_sig = Signature(32, has_first_last=True)
pkt_stream = pkt_sig.create()
print(pkt_stream.first)  # Signal(1)
print(pkt_stream.last)   # Signal(1)

# Full-featured stream: 64-bit payload, framing, 4-bit param, byte-enables
full_sig = Signature(64,
    has_first_last=True,
    param_shape=4,
    has_keep=True,
)
full_stream = full_sig.create()
print(full_stream.keep)   # Signal(8) — ceil(64/8) = 8 bytes
print(full_stream.param)  # Signal(4)
print(full_stream.p)      # Shortcut for full_stream.payload
```

### 2. Using a Buffer Pipeline Stage

```python
from amaranth import *
from amaranth.lib.wiring import connect
from amaranth_stream import Signature, Buffer, PipeValid, Pipeline

class MyDesign(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        sig = Signature(32, has_first_last=True)

        # Single buffer stage (registers both valid and ready paths)
        buf = Buffer(sig)
        m.submodules.buf = buf

        # Or use a declarative pipeline with multiple stages
        stage1 = PipeValid(sig)
        stage2 = Buffer(sig)
        pipe = Pipeline(stage1, stage2)
        m.submodules.pipe = pipe

        # Connect: source → pipe.i_stream, pipe.o_stream → sink
        return m
```

### 3. Simulation with BFMs

```python
from amaranth import *
from amaranth.sim import Simulator
from amaranth_stream import Signature, Buffer, StreamSimSender, StreamSimReceiver

sig = Signature(8, has_first_last=True)
dut = Buffer(sig)

sim = Simulator(dut)
sim.add_clock(1e-6)

async def testbench(ctx):
    sender = StreamSimSender(dut.i_stream)
    receiver = StreamSimReceiver(dut.o_stream)

    # Send a single beat
    await sender.send(ctx, 0xAB)
    beat = await receiver.recv(ctx)
    assert beat["payload"] == 0xAB

    # Send a complete packet with automatic first/last framing
    await sender.send_packet(ctx, [0x01, 0x02, 0x03])
    beats = await receiver.recv_packet(ctx)
    assert [b["payload"] for b in beats] == [0x01, 0x02, 0x03]
    assert beats[0]["first"] == 1
    assert beats[-1]["last"] == 1

    # Stress-test with random backpressure
    stress_sender = StreamSimSender(dut.i_stream, random_valid=True, seed=42)
    stress_receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=43)

sim.add_testbench(testbench)
with sim.write_vcd("test.vcd"):
    sim.run()
```

---

## Stream Protocol

### Valid/Ready Handshake

The stream protocol uses a **valid/ready** handshake, identical to AXI-Stream's TVALID/TREADY:

```
         ┌──────────┐         ┌──────────┐
         │  Source   │         │   Sink   │
         │          ├─valid──►│          │
         │          ├─payload─►│          │
         │          │◄─ready──┤          │
         └──────────┘         └──────────┘
```

A **transfer** occurs on a clock edge when **both** `valid` and `ready` are high:

```
        clk  ─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─
              └─┘ └─┘ └─┘ └─┘ └─┘ └─┘ └─┘
      valid  ─────┐           ┌───────────┐
                  └───────────┘           └───
      ready  ─┐       ┌───────────┐
              └───────┘           └───────────
    payload  ─────XXXX─────────────AAAA─BBBB──
                       ↑               ↑
                   transfer A      transfer B
```

### Optional Signals

| Signal | Direction | Width | Description |
|--------|-----------|-------|-------------|
| `payload` | Source → Sink | User-defined | Data payload |
| `valid` | Source → Sink | 1 | Source has data available |
| `ready` | Sink → Source | 1 | Sink can accept data |
| `first` | Source → Sink | 1 | First beat of a packet |
| `last` | Source → Sink | 1 | Last beat of a packet |
| `param` | Source → Sink | User-defined | Sideband parameter (constant per packet) |
| `keep` | Source → Sink | ⌈payload_width/8⌉ | Byte-enable mask |

### Transfer Rules

1. **Once `valid` is asserted, it must not be deasserted until a transfer occurs** (valid & ready).
2. **Once `valid` is asserted, `payload` (and `first`/`last`) must not change until transfer.**
3. **`ready` may be asserted/deasserted freely** — it has no persistence requirement.
4. **`first` and `last` define packet boundaries** — `first=1` on the first beat, `last=1` on the last beat. Single-beat packets have both `first=1` and `last=1`.

---

## API Reference

### Core — Signature & Interface

*Module: `amaranth_stream._base`*

#### Signature

```python
class Signature(wiring.Signature)
```

Extended stream signature with optional `first`/`last`, `param`, and `keep` members. This is the foundation of the entire library — every component accepts or produces `Signature` instances.

**Constructor:**

```python
Signature(
    payload_shape,           # ShapeLike — shape of the payload member
    *,
    always_valid=False,      # bool — drive valid to Const(1) in created Interface
    always_ready=False,      # bool — drive ready to Const(1) in created Interface
    has_first_last=False,    # bool — add first/last packet framing signals
    param_shape=None,        # ShapeLike or None — add param sideband member
    has_keep=False,          # bool — add keep byte-enable member
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `payload_shape` | `ShapeLike` | *(required)* | Shape of the payload member. Can be an integer (unsigned width), `Shape`, or any `ShapeLike`. |
| `always_valid` | `bool` | `False` | If `True`, the `Interface` created from this signature will have `valid` driven to `Const(1)`. |
| `always_ready` | `bool` | `False` | If `True`, the `Interface` created from this signature will have `ready` driven to `Const(1)`. |
| `has_first_last` | `bool` | `False` | If `True`, adds `first` (Out, 1-bit) and `last` (Out, 1-bit) members for packet framing. |
| `param_shape` | `ShapeLike` or `None` | `None` | If not `None`, adds a `param` (Out) sideband member with the given shape. |
| `has_keep` | `bool` | `False` | If `True`, adds a `keep` (Out) member with width `ceil(payload_width / 8)`. |

**Members (created in the signature):**

| Member | Direction | Shape | Condition |
|--------|-----------|-------|-----------|
| `payload` | `Out` | `payload_shape` | Always |
| `valid` | `Out` | 1 | Always |
| `ready` | `In` | 1 | Always |
| `first` | `Out` | 1 | `has_first_last=True` |
| `last` | `Out` | 1 | `has_first_last=True` |
| `param` | `Out` | `param_shape` | `param_shape is not None` |
| `keep` | `Out` | `ceil(payload_width/8)` | `has_keep=True` |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `payload_shape` | `ShapeLike` | The shape of the payload member |
| `payload_width` | `int` | The bit-width of the payload |
| `always_valid` | `bool` | Whether the stream always has a valid payload |
| `always_ready` | `bool` | Whether the stream is always ready |
| `has_first_last` | `bool` | Whether the stream has first/last framing |
| `param_shape` | `ShapeLike` or `None` | The shape of the param member |
| `has_keep` | `bool` | Whether the stream has a keep byte-enable |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `create(*, path=None, src_loc_at=0)` | `Interface` | Create an `Interface` from this signature |

**Example:**

```python
from amaranth_stream import Signature

# 32-bit stream with packet framing and 8-bit sideband parameter
sig = Signature(32, has_first_last=True, param_shape=8)
print(sig)
# stream.Signature(32, has_first_last=True, param_shape=8)

print(sig.payload_width)  # 32
print(sig.has_first_last)  # True

# Equality comparison
sig2 = Signature(32, has_first_last=True, param_shape=8)
assert sig == sig2
```

---

#### Interface

```python
class Interface
```

Concrete stream interface created from a `Signature`. Populates attributes from the signature members and optionally replaces `valid`/`ready` with `Const(1)`.

**Constructor:**

```python
Interface(signature, *, path=None, src_loc_at=0)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | The stream signature to create an interface from |
| `path` | `tuple` or `None` | Signal naming path |
| `src_loc_at` | `int` | Source location offset for error messages |

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | The signature this interface was created from |
| `payload` | `Signal` | Payload data signal |
| `valid` | `Signal` or `Const` | Valid handshake signal (may be `Const(1)` if `always_valid`) |
| `ready` | `Signal` or `Const` | Ready handshake signal (may be `Const(1)` if `always_ready`) |
| `p` | `Signal` | Shortcut alias for `payload` |
| `first` | `Signal` | *(only if `has_first_last`)* First beat marker |
| `last` | `Signal` | *(only if `has_first_last`)* Last beat marker |
| `param` | `Signal` | *(only if `param_shape is not None`)* Sideband parameter |
| `keep` | `Signal` | *(only if `has_keep`)* Byte-enable mask |

**Example:**

```python
from amaranth_stream import Signature

sig = Signature(16, always_valid=True, has_first_last=True)
stream = sig.create()

print(stream.valid)    # Const(1) — always valid
print(stream.payload)  # Signal(16)
print(stream.p)        # Same as stream.payload
print(stream.first)    # Signal(1)
```

---

#### core_to_extended

```python
def core_to_extended(core_sig) -> Signature
```

Convert an `amaranth.lib.stream.Signature` to an `amaranth_stream.Signature`.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `core_sig` | `amaranth.lib.stream.Signature` | The core Amaranth stream signature to convert |

**Returns:** `Signature` — An extended stream signature with the same `payload_shape`, `always_valid`, and `always_ready` flags.

**Raises:** `TypeError` if the input is not an `amaranth.lib.stream.Signature`.

**Example:**

```python
from amaranth.lib.stream import Signature as CoreSignature
from amaranth_stream import core_to_extended

core_sig = CoreSignature(8)
ext_sig = core_to_extended(core_sig)
# ext_sig is now an amaranth_stream.Signature(8)
```

---

#### connect_streams

```python
def connect_streams(m, src, dst, *, exclude=None)
```

Connect two stream interfaces combinationally. Wires `src` (source/initiator) to `dst` (destination/target), connecting handshake signals, payload, and any optional members that both interfaces share.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `m` | `Module` | *(required)* | The module to add combinational statements to |
| `src` | stream interface | *(required)* | Source stream (drives payload, valid, and forward sideband signals) |
| `dst` | stream interface | *(required)* | Destination stream (drives ready) |
| `exclude` | `set` of `str` or `None` | `None` | Optional set of member names to skip when connecting |

**Behavior:** Only members present on **both** `src` and `dst` are connected. If one side has `first`/`last` but the other does not, those signals are silently skipped. The `exclude` parameter can suppress connection of any member by name.

**Example:**

```python
from amaranth_stream import Signature, connect_streams

sig = Signature(32, has_first_last=True)
src = sig.create()
dst = sig.create()

# In elaborate():
connect_streams(m, src, dst)

# Skip param connection:
connect_streams(m, src, dst, exclude={"param"})
```

---

### Simulation BFMs

*Module: `amaranth_stream.sim`*

Bus Functional Models for driving and consuming streams in Amaranth async testbenches. These BFMs use `ctx.tick().sample()` to capture signal values at the exact clock edge, avoiding race conditions between concurrent testbenches.

#### StreamSimSender

```python
class StreamSimSender
```

Simulation BFM that drives a stream source (initiator side).

**Constructor:**

```python
StreamSimSender(
    stream,                  # Interface — the stream interface to drive
    *,
    domain="sync",           # str — clock domain name
    random_valid=False,      # bool — randomly deassert valid for stress testing
    seed=None,               # int or None — RNG seed for reproducible random delays
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stream` | `Interface` | *(required)* | The stream interface to drive. Drives `payload`, `valid`, and optionally `first`, `last`, `param`, `keep`. |
| `domain` | `str` | `"sync"` | Clock domain name |
| `random_valid` | `bool` | `False` | If `True`, randomly deassert `valid` to stress-test backpressure handling |
| `seed` | `int` or `None` | `None` | RNG seed for reproducible random delays |

**Methods:**

| Method | Description |
|--------|-------------|
| `await send(ctx, payload, *, first=None, last=None, param=None, keep=None)` | Send a single beat. Drives `payload` and `valid`, waits for handshake, then deasserts `valid`. |
| `await send_packet(ctx, payloads, *, param=None)` | Send a complete packet with automatic `first`/`last` framing. |

**`send()` Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ctx` | testbench context | *(required)* | The `ctx` from `async def testbench(ctx)` |
| `payload` | `int` | *(required)* | Payload value to send |
| `first` | `int` or `None` | `None` | Value for `first` signal (if stream has one) |
| `last` | `int` or `None` | `None` | Value for `last` signal (if stream has one) |
| `param` | `int` or `None` | `None` | Value for `param` signal (if stream has one) |
| `keep` | `int` or `None` | `None` | Value for `keep` signal (if stream has one) |

**`send_packet()` Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ctx` | testbench context | *(required)* | The `ctx` from `async def testbench(ctx)` |
| `payloads` | iterable of `int` | *(required)* | Sequence of payload values forming the packet |
| `param` | `int` or `None` | `None` | Constant `param` value for every beat |

**Example:**

```python
async def testbench(ctx):
    sender = StreamSimSender(dut.i_stream, random_valid=True, seed=42)

    # Single beat
    await sender.send(ctx, 0xFF, first=1, last=1)

    # Multi-beat packet (first/last set automatically)
    await sender.send_packet(ctx, [0x01, 0x02, 0x03, 0x04])
```

---

#### StreamSimReceiver

```python
class StreamSimReceiver
```

Simulation BFM that consumes a stream sink (responder side).

**Constructor:**

```python
StreamSimReceiver(
    stream,                  # Interface — the stream interface to consume
    *,
    domain="sync",           # str — clock domain name
    random_ready=False,      # bool — randomly deassert ready for stress testing
    seed=None,               # int or None — RNG seed for reproducible random delays
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stream` | `Interface` | *(required)* | The stream interface to consume. Drives `ready` and reads `payload`, `valid`, and optional signals. |
| `domain` | `str` | `"sync"` | Clock domain name |
| `random_ready` | `bool` | `False` | If `True`, randomly deassert `ready` to stress-test flow control |
| `seed` | `int` or `None` | `None` | RNG seed for reproducible random delays |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `await recv(ctx)` | `dict` | Receive a single beat. Returns dict with `"payload"` and optionally `"first"`, `"last"`, `"param"`, `"keep"`. |
| `await recv_packet(ctx)` | `list[dict]` | Receive beats until `last=1`. Returns list of beat dicts. |
| `await expect_packet(ctx, expected_payloads)` | `None` | Receive a packet and assert payloads match. Raises `AssertionError` on mismatch. |

**`recv()` Return Value:**

```python
{
    "payload": int,     # Always present
    "first": int,       # Present if stream has first/last
    "last": int,        # Present if stream has first/last
    "param": int,       # Present if stream has param
    "keep": int,        # Present if stream has keep
}
```

**Example:**

```python
async def testbench(ctx):
    receiver = StreamSimReceiver(dut.o_stream, random_ready=True, seed=43)

    # Receive single beat
    beat = await receiver.recv(ctx)
    assert beat["payload"] == 0xAB

    # Receive complete packet
    beats = await receiver.recv_packet(ctx)
    payloads = [b["payload"] for b in beats]

    # Assert expected packet
    await receiver.expect_packet(ctx, [0x01, 0x02, 0x03])
```

---

### Buffering & Pipeline

*Module: `amaranth_stream.buffer`, `amaranth_stream.pipeline`*

Components for breaking combinational paths and building multi-stage pipelines.

#### Buffer

```python
class Buffer(wiring.Component)
```

Pipeline register that breaks combinational paths. Can register the forward path (payload/valid), the backward path (ready), or both.

**Constructor:**

```python
Buffer(
    signature,               # Signature — stream signature for both ports
    pipe_valid=True,         # bool — register the forward path
    pipe_ready=True,         # bool — register the backward path
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature for both input and output ports |
| `pipe_valid` | `bool` | `True` | If `True`, register payload, valid, first, last, param, keep |
| `pipe_ready` | `bool` | `True` | If `True`, register the ready path |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream |

**Behavior:**

| `pipe_valid` | `pipe_ready` | Behavior |
|:---:|:---:|---|
| `True` | `True` | Full skid buffer — chains PipeValid → PipeReady internally. 2-cycle latency, full throughput. |
| `True` | `False` | Forward-registered — registers payload/valid. Ready is combinational pass-through. 1-cycle latency. |
| `False` | `True` | Backward-registered — registers ready. Forward path is combinational with bypass register. |
| `False` | `False` | Wire-through — no registers, zero latency. |

**Example:**

```python
from amaranth_stream import Signature, Buffer

sig = Signature(32, has_first_last=True)

# Full pipeline register (breaks both paths)
buf = Buffer(sig)

# Forward-only register
buf_fwd = Buffer(sig, pipe_valid=True, pipe_ready=False)

# Backward-only register
buf_bwd = Buffer(sig, pipe_valid=False, pipe_ready=True)
```

---

#### PipeValid

```python
class PipeValid(Buffer)
```

Convenience wrapper: forward-registered pipeline stage. Registers `payload`, `valid`, `first`, `last`, `param`, `keep`. Ready is combinational pass-through.

**Constructor:**

```python
PipeValid(signature)  # Signature — stream signature
```

Equivalent to `Buffer(signature, pipe_valid=True, pipe_ready=False)`.

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream |

**Example:**

```python
from amaranth_stream import Signature, PipeValid

sig = Signature(16)
stage = PipeValid(sig)
# stage.i_stream → registered → stage.o_stream
```

---

#### PipeReady

```python
class PipeReady(Buffer)
```

Convenience wrapper: backward-registered pipeline stage. Ready is registered. Forward path is combinational with a bypass register for when downstream was not ready.

**Constructor:**

```python
PipeReady(signature)  # Signature — stream signature
```

Equivalent to `Buffer(signature, pipe_valid=False, pipe_ready=True)`.

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream |

**Example:**

```python
from amaranth_stream import Signature, PipeReady

sig = Signature(16)
stage = PipeReady(sig)
```

---

#### Delay

```python
class Delay(wiring.Component)
```

N-stage pipeline delay using chained `PipeValid` stages.

**Constructor:**

```python
Delay(
    signature,               # Signature — stream signature
    stages=1,                # int — number of pipeline stages (0 = wire-through)
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature for both input and output ports |
| `stages` | `int` | `1` | Number of pipeline stages. 0 means wire-through. Must be ≥ 0. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream |

**Behavior:** Creates `stages` chained `PipeValid` instances. Each stage adds 1 cycle of latency. With `stages=0`, the component is a wire-through with zero latency.

**Example:**

```python
from amaranth_stream import Signature, Delay

sig = Signature(8)

# 3-cycle delay
delay = Delay(sig, stages=3)

# Wire-through (no delay)
passthrough = Delay(sig, stages=0)
```

---

#### Pipeline

```python
class Pipeline(wiring.Component)
```

Declarative pipeline builder. Chains stages by connecting each stage's `o_stream` to the next stage's `i_stream`.

**Constructor:**

```python
Pipeline(*stages)  # wiring.Component instances with i_stream/o_stream ports
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `*stages` | `wiring.Component` | One or more component instances, each with `i_stream` and `o_stream` ports. At least one stage is required. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(first_stage.i_stream.signature)` | Pipeline input, matching the first stage's input signature |
| `o_stream` | `Out(last_stage.o_stream.signature)` | Pipeline output, matching the last stage's output signature |

**Behavior:** Adds all stages as submodules and connects them in series: `i_stream → stage_0 → stage_1 → ... → stage_N-1 → o_stream`.

**Example:**

```python
from amaranth_stream import Signature, Buffer, PipeValid, Pipeline

sig = Signature(32, has_first_last=True)

# Build a 3-stage pipeline
pipe = Pipeline(
    PipeValid(sig),
    Buffer(sig),
    PipeValid(sig),
)
# pipe.i_stream → PipeValid → Buffer → PipeValid → pipe.o_stream
```

---

#### BufferizeEndpoints

```python
class BufferizeEndpoints(wiring.Component)
```

Wraps a component, inserting `Buffer` stages on all stream ports. For each `In` stream port, a Buffer is inserted before the component. For each `Out` stream port, a Buffer is inserted after the component.

**Constructor:**

```python
BufferizeEndpoints(
    component,               # wiring.Component — the component to wrap
    *,
    pipe_valid=True,         # bool — register forward path in buffers
    pipe_ready=True,         # bool — register backward path in buffers
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `component` | `wiring.Component` | *(required)* | The component to wrap |
| `pipe_valid` | `bool` | `True` | Register the forward path in inserted buffers |
| `pipe_ready` | `bool` | `True` | Register the backward path in inserted buffers |

**Ports:** Same as the wrapped component's stream ports.

**Example:**

```python
from amaranth_stream import Signature, Buffer, BufferizeEndpoints

sig = Signature(32)
core = Buffer(sig, pipe_valid=True, pipe_ready=False)

# Wrap with full buffers on all endpoints
wrapped = BufferizeEndpoints(core)
# wrapped.i_stream → Buffer → core.i_stream → core.o_stream → Buffer → wrapped.o_stream
```

---

### FIFOs & CDC

*Module: `amaranth_stream.fifo`, `amaranth_stream.cdc`*

FIFO and clock-domain crossing components with stream interfaces.

#### StreamFIFO

```python
class StreamFIFO(wiring.Component)
```

Synchronous FIFO with stream interfaces. Packs all stream signals (payload, first, last, param, keep) into a single wide data word for storage, and unpacks them on the read side.

**Constructor:**

```python
StreamFIFO(
    signature,               # Signature — stream signature
    depth,                   # int — FIFO depth in entries (≥ 0)
    *,
    buffered=True,           # bool — use SyncFIFOBuffered (block RAM compatible)
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature for both input and output ports |
| `depth` | `int` | *(required)* | FIFO depth in entries. Must be ≥ 0. |
| `buffered` | `bool` | `True` | If `True`, uses `SyncFIFOBuffered` (registered output, block RAM compatible). If `False`, uses `SyncFIFO` (combinational output). |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream (write side) |
| `o_stream` | `Out(signature)` | Output stream (read side) |
| `level` | `Out(range(depth + 1))` | Number of entries currently in the FIFO |

**Example:**

```python
from amaranth_stream import Signature, StreamFIFO

sig = Signature(32, has_first_last=True)

# 256-entry buffered FIFO
fifo = StreamFIFO(sig, depth=256)

# Unbuffered FIFO (combinational read output)
fifo_comb = StreamFIFO(sig, depth=64, buffered=False)
```

---

#### StreamAsyncFIFO

```python
class StreamAsyncFIFO(wiring.Component)
```

Asynchronous (cross-domain) FIFO with stream interfaces. Packs all stream signals into a single wide data word for safe cross-domain transfer.

**Constructor:**

```python
StreamAsyncFIFO(
    signature,               # Signature — stream signature
    depth,                   # int — FIFO depth (rounded to power of 2 for AsyncFIFO)
    *,
    w_domain="write",        # str — write clock domain
    r_domain="read",         # str — read clock domain
    buffered=True,           # bool — use AsyncFIFOBuffered
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature for both input and output ports |
| `depth` | `int` | *(required)* | FIFO depth in entries. For `AsyncFIFO`, rounded up to next power of 2. |
| `w_domain` | `str` | `"write"` | Write clock domain |
| `r_domain` | `str` | `"read"` | Read clock domain |
| `buffered` | `bool` | `True` | If `True`, uses `AsyncFIFOBuffered`. If `False`, uses `AsyncFIFO`. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream (in `w_domain`) |
| `o_stream` | `Out(signature)` | Output stream (in `r_domain`) |

**Example:**

```python
from amaranth_stream import Signature, StreamAsyncFIFO

sig = Signature(64, has_first_last=True, has_keep=True)

# Cross 100MHz → 200MHz domain
async_fifo = StreamAsyncFIFO(sig, depth=32,
    w_domain="clk100", r_domain="clk200")
```

---

#### StreamCDC

```python
class StreamCDC(wiring.Component)
```

Automatic clock-domain crossing for streams. When `w_domain == r_domain`, instantiates a `Buffer` (simple pipeline register). When the domains differ, instantiates a `StreamAsyncFIFO` for safe cross-domain transfer.

**Constructor:**

```python
StreamCDC(
    signature,               # Signature — stream signature
    *,
    depth=8,                 # int — FIFO depth for cross-domain case
    w_domain="sync",         # str — write clock domain
    r_domain="sync",         # str — read clock domain
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature for both input and output ports |
| `depth` | `int` | `8` | FIFO depth for the cross-domain case |
| `w_domain` | `str` | `"sync"` | Write clock domain |
| `r_domain` | `str` | `"sync"` | Read clock domain |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream (in `w_domain`) |
| `o_stream` | `Out(signature)` | Output stream (in `r_domain`) |

**Behavior:**

| Condition | Internal Component |
|-----------|-------------------|
| `w_domain == r_domain` | `Buffer(signature)` |
| `w_domain != r_domain` | `StreamAsyncFIFO(signature, depth, ...)` |

**Example:**

```python
from amaranth_stream import Signature, StreamCDC

sig = Signature(32)

# Same domain: becomes a simple Buffer
cdc_same = StreamCDC(sig, w_domain="sync", r_domain="sync")

# Cross-domain: becomes an AsyncFIFO
cdc_cross = StreamCDC(sig, depth=16, w_domain="fast", r_domain="slow")
```

---

### Width Conversion

*Module: `amaranth_stream.converter`*

Components for converting between streams of different payload widths.

#### StreamConverter

```python
class StreamConverter(wiring.Component)
```

Integer-ratio width converter for flat payloads. Converts between streams where the wider payload width is an exact integer multiple of the narrower payload width.

**Constructor:**

```python
StreamConverter(
    i_signature,             # Signature — input stream signature
    o_signature,             # Signature — output stream signature
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input stream signature |
| `o_signature` | `Signature` | Output stream signature. Width must be an integer multiple of the other. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(i_signature)` | Input stream |
| `o_stream` | `Out(o_signature)` | Output stream |

**Behavior:**

| Mode | Condition | Description |
|------|-----------|-------------|
| Identity | `i_width == o_width` | Wire-through |
| Upsize | `o_width > i_width` | Collects `ratio` narrow input beats into one wide output beat using a shift register |
| Downsize | `i_width > o_width` | Splits one wide input beat into `ratio` narrow output beats |

**Raises:** `ValueError` if widths are not integer multiples.

**Example:**

```python
from amaranth_stream import Signature, StreamConverter

# 8-bit → 32-bit (4:1 upsize)
i_sig = Signature(8, has_first_last=True)
o_sig = Signature(32, has_first_last=True)
upsize = StreamConverter(i_sig, o_sig)

# 32-bit → 8-bit (1:4 downsize)
downsize = StreamConverter(o_sig, i_sig)
```

---

#### StrideConverter

```python
class StrideConverter(wiring.Component)
```

Structured field-aware width converter. Handles non-integer ratios by padding to LCM. For integer ratios, uses the same logic as `StreamConverter`.

**Constructor:**

```python
StrideConverter(
    i_signature,             # Signature — input stream signature
    o_signature,             # Signature — output stream signature
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input stream signature |
| `o_signature` | `Signature` | Output stream signature (any width ratio) |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(i_signature)` | Input stream |
| `o_stream` | `Out(o_signature)` | Output stream |

**Behavior:** Uses a FILL/DRAIN FSM. During FILL, collects `i_ratio = lcm(i_width, o_width) / i_width` input beats into an LCM-sized buffer. During DRAIN, outputs `o_ratio = lcm(i_width, o_width) / o_width` beats from the buffer.

**Example:**

```python
from amaranth_stream import Signature, StrideConverter

# 12-bit → 8-bit (non-integer ratio, LCM = 24)
i_sig = Signature(12)
o_sig = Signature(8)
conv = StrideConverter(i_sig, o_sig)
# Collects 2 × 12-bit = 24 bits, outputs 3 × 8-bit = 24 bits
```

---

#### Gearbox

```python
class Gearbox(wiring.Component)
```

Non-integer ratio width converter using a shift-register approach. Converts between streams of arbitrary widths (e.g., 10b→8b or 8b→10b) using a shift register buffer with level tracking.

**Constructor:**

```python
Gearbox(
    i_width,                 # int — input data width in bits
    o_width,                 # int — output data width in bits
    *,
    has_first_last=False,    # bool — include first/last framing signals
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `i_width` | `int` | *(required)* | Input data width in bits |
| `o_width` | `int` | *(required)* | Output data width in bits |
| `has_first_last` | `bool` | `False` | If `True`, include first/last framing signals |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(Signature(i_width))` | Input stream |
| `o_stream` | `Out(Signature(o_width))` | Output stream |

**Behavior:** Maintains a buffer of `lcm(i_width, o_width)` bits with a level counter. Accepts input when there's enough space (`level + i_width ≤ buffer_size`). Produces output when there's enough data (`level ≥ o_width`). Can accept and produce simultaneously.

**Example:**

```python
from amaranth_stream import Gearbox

# 10b/8b gearbox (e.g., for 8b10b encoding)
gb = Gearbox(10, 8)

# 8b/10b gearbox (reverse direction)
gb_rev = Gearbox(8, 10)
```

---

#### StreamCast

```python
class StreamCast(wiring.Component)
```

Zero-cost bit reinterpretation between streams of the same bit width. Simply wires input payload bits to output payload bits with a different shape interpretation. Passes through valid/ready/first/last/param/keep unchanged.

**Constructor:**

```python
StreamCast(
    i_signature,             # Signature — input stream signature
    o_signature,             # Signature — output stream signature (same bit width)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input stream signature |
| `o_signature` | `Signature` | Output stream signature. Must have the same payload bit width. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(i_signature)` | Input stream |
| `o_stream` | `Out(o_signature)` | Output stream |

**Raises:** `ValueError` if payload bit widths differ.

**Example:**

```python
from amaranth.hdl import signed
from amaranth_stream import Signature, StreamCast

# Reinterpret unsigned 16-bit as signed 16-bit
i_sig = Signature(16)
o_sig = Signature(signed(16))
cast = StreamCast(i_sig, o_sig)
```

---

#### Pack

```python
class Pack(wiring.Component)
```

Collects N narrow beats into 1 wide beat. The output payload width is `input_width × n`.

**Constructor:**

```python
Pack(
    i_signature,             # Signature — input (narrow) stream signature
    n,                       # int — number of beats to pack (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input (narrow) stream signature |
| `n` | `int` | Number of beats to pack. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(i_signature)` | Input stream (narrow) |
| `o_stream` | `Out(o_signature)` | Output stream (wide, width = `i_width × n`) |

**Behavior:** Collects `n` input beats into a shift register, then outputs one wide beat. Preserves `first` from the first input beat and `last` from the last input beat. Keep bits are concatenated.

**Example:**

```python
from amaranth_stream import Signature, Pack

# Pack 4 × 8-bit beats into 1 × 32-bit beat
i_sig = Signature(8, has_first_last=True)
pack = Pack(i_sig, 4)
# pack.o_stream has 32-bit payload
```

---

#### Unpack

```python
class Unpack(wiring.Component)
```

Splits 1 wide beat into N narrow beats. The input payload width is `output_width × n`.

**Constructor:**

```python
Unpack(
    o_signature,             # Signature — output (narrow) stream signature
    n,                       # int — number of beats to unpack (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `o_signature` | `Signature` | Output (narrow) stream signature |
| `n` | `int` | Number of beats to unpack. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(i_signature)` | Input stream (wide, width = `o_width × n`) |
| `o_stream` | `Out(o_signature)` | Output stream (narrow) |

**Behavior:** Latches one wide input beat, then outputs `n` narrow beats sequentially. `first` is set on the first output beat (counter == 0), `last` on the last (counter == n-1). Keep bits are sliced accordingly.

**Example:**

```python
from amaranth_stream import Signature, Unpack

# Unpack 1 × 32-bit beat into 4 × 8-bit beats
o_sig = Signature(8, has_first_last=True)
unpack = Unpack(o_sig, 4)
# unpack.i_stream has 32-bit payload
```

---

#### ByteEnableSerializer

```python
class ByteEnableSerializer(wiring.Component)
```

Serialize a wide stream with byte enables into a narrow stream of valid bytes. Converts a wide input stream (e.g. 256-bit with 32-byte keep mask) into a narrow output stream (e.g. 8-bit) by emitting only the bytes/chunks whose corresponding `keep` bits are set, skipping those where `keep=0`.

This is useful for things like PCIe TLP sniffers that need to serialize a 256-bit stream with sparse byte enables down to an 8-bit byte stream.

**Constructor:**

```python
ByteEnableSerializer(
    i_width,                 # int — input data width in bits (multiple of 8)
    o_width=8,               # int — output data width in bits (multiple of 8)
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `i_width` | `int` | *(required)* | Input data width in bits. Must be a multiple of 8. |
| `o_width` | `int` | `8` | Output data width in bits. Must be a multiple of 8. `i_width` must be ≥ `o_width`. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(Signature(i_width, has_first_last=True, has_keep=True))` | Input stream with byte enables |
| `o_stream` | `Out(Signature(o_width, has_first_last=True))` | Output stream (all output bytes are valid, no keep needed) |

**Behavior:** Uses an IDLE/DRAIN FSM. In IDLE, latches the input beat. In DRAIN, iterates through chunks, emitting only those with valid keep bits. `first` is set on the first valid output chunk, `last` on the last valid output chunk.

**Example:**

```python
from amaranth_stream import ByteEnableSerializer

# Serialize 256-bit stream with byte enables to 8-bit byte stream
ser = ByteEnableSerializer(256, 8)

# Serialize 128-bit stream to 32-bit chunks
ser32 = ByteEnableSerializer(128, 32)
```

---

### Routing

*Module: `amaranth_stream.routing`*

Components for routing streams between multiple sources and sinks.

#### StreamMux

```python
class StreamMux(wiring.Component)
```

N:1 multiplexer. Selects one of N inputs via `sel`.

**Constructor:**

```python
StreamMux(
    signature,               # Signature — stream signature (identical for all ports)
    n,                       # int — number of input streams (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (identical for all ports) |
| `n` | `int` | Number of input streams. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream__0` .. `i_stream__N-1` | `In(signature)` | Input streams |
| `o_stream` | `Out(signature)` | Output stream |
| `sel` | `In(range(n))` | Selects which input to route to the output |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `n` | `int` | Number of input streams |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `get_input(i)` | `Interface` | Return the i-th input stream interface |

**Behavior:** Routes all forward signals (payload, valid, first, last, param, keep) from the selected input to the output. Ready is routed from the output back to the selected input only. Non-selected inputs have `ready=0`.

**Example:**

```python
from amaranth_stream import Signature, StreamMux

sig = Signature(32, has_first_last=True)
mux = StreamMux(sig, n=4)

# Access inputs
input_0 = mux.get_input(0)  # or mux.i_stream__0
input_1 = mux.get_input(1)  # or mux.i_stream__1
```

---

#### StreamDemux

```python
class StreamDemux(wiring.Component)
```

1:N demultiplexer. Routes input to one of N outputs via `sel`.

**Constructor:**

```python
StreamDemux(
    signature,               # Signature — stream signature (identical for all ports)
    n,                       # int — number of output streams (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (identical for all ports) |
| `n` | `int` | Number of output streams. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream__0` .. `o_stream__N-1` | `Out(signature)` | Output streams |
| `sel` | `In(range(n))` | Selects which output receives the input data |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `n` | `int` | Number of output streams |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `get_output(i)` | `Interface` | Return the i-th output stream interface |

**Behavior:** All outputs receive the same payload/sideband data, but only the selected output gets `valid`. Ready comes from the selected output only.

**Example:**

```python
from amaranth_stream import Signature, StreamDemux

sig = Signature(32)
demux = StreamDemux(sig, n=3)

# Access outputs
output_0 = demux.get_output(0)  # or demux.o_stream__0
```

---

#### StreamGate

```python
class StreamGate(wiring.Component)
```

Enable/disable gate for a stream. When `en=1`, the stream passes through. When `en=0`, the stream is either backpressured or discarded.

**Constructor:**

```python
StreamGate(
    signature,               # Signature — stream signature
    discard=False,           # bool — discard mode when gated
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature for both input and output ports |
| `discard` | `bool` | `False` | If `True`, consume and discard data when gated (`en=0`). If `False`, apply backpressure. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream |
| `en` | `In(1)` | Enable signal. When high, stream passes through. |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `discard` | `bool` | Whether discard mode is enabled |

**Behavior:**

| `en` | `discard` | Behavior |
|:---:|:---:|---|
| `1` | — | Pass-through: valid and ready wired through |
| `0` | `False` | Backpressure: `o_stream.valid=0`, `i_stream.ready=0` |
| `0` | `True` | Discard: `o_stream.valid=0`, `i_stream.ready=1` (data consumed and dropped) |

**Example:**

```python
from amaranth_stream import Signature, StreamGate

sig = Signature(32)

# Backpressure gate (default)
gate = StreamGate(sig)

# Discard gate
gate_discard = StreamGate(sig, discard=True)
```

---

#### StreamSplitter

```python
class StreamSplitter(wiring.Component)
```

1:N broadcast/fanout. Synchronized — a transfer only occurs when **ALL** outputs are ready. All outputs receive the same data simultaneously.

**Constructor:**

```python
StreamSplitter(
    signature,               # Signature — stream signature (identical for all ports)
    n,                       # int — number of output streams (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (identical for all ports) |
| `n` | `int` | Number of output streams. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream__0` .. `o_stream__N-1` | `Out(signature)` | Output streams (all receive the same data) |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `n` | `int` | Number of output streams |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `get_output(i)` | `Interface` | Return the i-th output stream interface |

**Behavior:** Computes `all_ready = AND(output_0.ready, output_1.ready, ...)`. Input `ready` is `all_ready`. All outputs get `valid = input.valid & all_ready`. This ensures atomic broadcast — either all outputs receive the beat or none do.

**Example:**

```python
from amaranth_stream import Signature, StreamSplitter

sig = Signature(32, has_first_last=True)
splitter = StreamSplitter(sig, n=3)
# All 3 outputs receive identical data simultaneously
```

---

#### StreamJoiner

```python
class StreamJoiner(wiring.Component)
```

N:1 interleaved join. Round-robin combining of N inputs.

**Constructor:**

```python
StreamJoiner(
    signature,               # Signature — stream signature (identical for all ports)
    n,                       # int — number of input streams (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (identical for all ports) |
| `n` | `int` | Number of input streams. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream__0` .. `i_stream__N-1` | `In(signature)` | Input streams |
| `o_stream` | `Out(signature)` | Output stream |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `n` | `int` | Number of input streams |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `get_input(i)` | `Interface` | Return the i-th input stream interface |

**Behavior:** Uses a round-robin counter that advances on each successful transfer. Connects the current input to the output. Non-selected inputs have `ready=0`.

**Example:**

```python
from amaranth_stream import Signature, StreamJoiner

sig = Signature(16)
joiner = StreamJoiner(sig, n=4)
# Interleaves beats from 4 inputs in round-robin order
```

---

### Packet Processing

*Module: `amaranth_stream.packet`*

Components for packet-level stream processing including header insertion/extraction, atomic packet buffering, and packet boundary manipulation.

#### HeaderLayout

```python
class HeaderLayout
```

Declarative header definition. Describes the fields of a packet header with their bit widths and byte offsets.

**Constructor:**

```python
HeaderLayout(fields)  # dict — mapping of field_name → (width, byte_offset)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `fields` | `dict` | Mapping of field name → `(width_in_bits, byte_offset)`. |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `struct_layout` | `StructLayout` | Amaranth `StructLayout` for the header fields |
| `byte_length` | `int` | Total header size in bytes (computed from max field end) |
| `fields` | `dict` | The original fields dict |

**Example:**

```python
from amaranth_stream import HeaderLayout

# Ethernet-like header: 6-byte dst + 6-byte src + 2-byte ethertype
header = HeaderLayout({
    "dst_mac":   (48, 0),   # 48 bits at byte offset 0
    "src_mac":   (48, 6),   # 48 bits at byte offset 6
    "ethertype": (16, 12),  # 16 bits at byte offset 12
})
print(header.byte_length)  # 14
print(header.struct_layout)
```

---

#### Packetizer

```python
class Packetizer(wiring.Component)
```

Inserts header beats before payload. Latches header on first beat.

**Constructor:**

```python
Packetizer(
    header_layout,           # HeaderLayout — header definition
    payload_signature,       # Signature — stream signature (must have has_first_last=True)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `header_layout` | `HeaderLayout` | Header definition |
| `payload_signature` | `Signature` | Stream signature. Must have `has_first_last=True`. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(payload_signature)` | Payload data input |
| `o_stream` | `Out(payload_signature)` | Header + payload data output |
| `header` | `In(header_layout.struct_layout)` | Header fields to insert |

**Behavior:** Uses a HEADER/PAYLOAD FSM. In HEADER state, emits `ceil(header_bits / payload_width)` header beats from the `header` port. Sets `first=1` on the first header beat. In PAYLOAD state, passes through payload beats with `first=0`. Returns to HEADER on `last`.

**Example:**

```python
from amaranth_stream import Signature, HeaderLayout, Packetizer

header = HeaderLayout({
    "type": (8, 0),
    "length": (16, 1),
})
sig = Signature(32, has_first_last=True)
pkt = Packetizer(header, sig)

# In elaborate:
# m.d.comb += [
#     pkt.header.type.eq(0x01),
#     pkt.header.length.eq(64),
# ]
```

---

#### Depacketizer

```python
class Depacketizer(wiring.Component)
```

Extracts header from packet start. Strips header beats and outputs payload only.

**Constructor:**

```python
Depacketizer(
    header_layout,           # HeaderLayout — header definition
    payload_signature,       # Signature — stream signature (must have has_first_last=True)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `header_layout` | `HeaderLayout` | Header definition |
| `payload_signature` | `Signature` | Stream signature. Must have `has_first_last=True`. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(payload_signature)` | Header + payload data input |
| `o_stream` | `Out(payload_signature)` | Payload only output |
| `header` | `Out(header_layout.struct_layout)` | Extracted header fields |

**Behavior:** Uses a HEADER/PAYLOAD FSM. In HEADER state, consumes `ceil(header_bits / payload_width)` beats and stores them. In PAYLOAD state, passes through payload beats with `first=1` on the first payload beat. Header fields are continuously driven from the stored bits.

**Example:**

```python
from amaranth_stream import Signature, HeaderLayout, Depacketizer

header = HeaderLayout({
    "type": (8, 0),
    "length": (16, 1),
})
sig = Signature(32, has_first_last=True)
depkt = Depacketizer(header, sig)

# In testbench:
# header_type = depkt.header.type  # extracted from packet
```

---

#### PacketFIFO

```python
class PacketFIFO(wiring.Component)
```

Atomic packet FIFO. Only releases complete packets. Uses a data FIFO for beat storage and a separate packet-length FIFO for tracking complete packets.

**Constructor:**

```python
PacketFIFO(
    signature,               # Signature — stream signature (must have has_first_last=True)
    payload_depth,           # int — max payload beats
    packet_depth=16,         # int — max buffered packets
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature. Must have `has_first_last=True`. |
| `payload_depth` | `int` | *(required)* | Maximum number of payload beats the data FIFO can hold |
| `packet_depth` | `int` | `16` | Maximum number of complete packets that can be buffered |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream |
| `packet_count` | `Out(range(packet_depth + 1))` | Number of complete packets available for reading |

**Behavior:** On the write side, beats are stored in the data FIFO. When `last` is seen, the beat count is committed to the packet-length FIFO. On the read side, a packet is only started when the packet-length FIFO has an entry. The output `first`/`last` are regenerated from the stored beat count.

**Example:**

```python
from amaranth_stream import Signature, PacketFIFO

sig = Signature(32, has_first_last=True)

# Buffer up to 1024 beats, 16 packets
pkt_fifo = PacketFIFO(sig, payload_depth=1024, packet_depth=16)
```

---

#### PacketStatus

```python
class PacketStatus(wiring.Component)
```

Packet boundary tracker. Tap-only (non-consuming) — does NOT drive `ready`.

**Constructor:**

```python
PacketStatus(signature)  # Signature — stream signature (must have has_first_last=True)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature. Must have `has_first_last=True`. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `stream` | `In(signature)` | Tap-only stream (does NOT drive ready) |
| `in_packet` | `Out(1)` | High when inside a packet (between first and last) |

**Behavior:** Sets `in_packet` high on `first` transfer, clears it on `last` transfer. This is a passive monitor — it does not affect the stream's flow control.

**Example:**

```python
from amaranth_stream import Signature, PacketStatus

sig = Signature(32, has_first_last=True)
status = PacketStatus(sig)
# status.in_packet is high between first and last beats
```

---

#### Stitcher

```python
class Stitcher(wiring.Component)
```

Groups N consecutive packets into one by suppressing intermediate `first`/`last` signals.

**Constructor:**

```python
Stitcher(
    signature,               # Signature — stream signature (must have has_first_last=True)
    n,                       # int — number of packets to stitch (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature. Must have `has_first_last=True`. |
| `n` | `int` | Number of packets to stitch together. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream with stitched packets |

**Behavior:** Counts packets using a modulo-N counter. `first` is only passed through on the first beat of the first packet (counter == 0). `last` is only passed through on the last beat of the Nth packet (counter == N-1). All other `first`/`last` signals are suppressed.

**Example:**

```python
from amaranth_stream import Signature, Stitcher

sig = Signature(32, has_first_last=True)

# Stitch 4 packets into 1
stitcher = Stitcher(sig, n=4)
# Input:  [pkt1][pkt2][pkt3][pkt4] → Output: [pkt1+pkt2+pkt3+pkt4]
```

---

#### LastInserter

```python
class LastInserter(wiring.Component)
```

Injects `last=1` every N beats, creating fixed-size packets from a continuous stream.

**Constructor:**

```python
LastInserter(
    signature,               # Signature — stream signature (must have has_first_last=True)
    n,                       # int — packet length in beats (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature. Must have `has_first_last=True`. |
| `n` | `int` | Packet length in beats. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream with injected first/last |

**Behavior:** Uses a modulo-N beat counter. Sets `first=1` when counter == 0, `last=1` when counter == N-1. The input's `first`/`last` signals are overridden.

**Example:**

```python
from amaranth_stream import Signature, LastInserter

sig = Signature(8, has_first_last=True)

# Create 64-byte packets from continuous stream
inserter = LastInserter(sig, n=64)
```

---

#### LastOnTimeout

```python
class LastOnTimeout(wiring.Component)
```

Injects `last=1` after a configurable idle timeout. Useful for creating packet boundaries when the source doesn't provide them reliably.

**Constructor:**

```python
LastOnTimeout(
    signature,               # Signature — stream signature (must have has_first_last=True)
    timeout,                 # int — idle cycles before injecting last (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature. Must have `has_first_last=True`. |
| `timeout` | `int` | Number of idle cycles before injecting `last`. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream with timeout-injected last |

**Behavior:** Tracks whether we're inside a packet (between `first` and `last`). When inside a packet and no transfer occurs for `timeout` consecutive cycles, forces `last=1` on the next transfer. The `first` signal passes through unchanged. The `last` output is `input.last | force_last`.

**Example:**

```python
from amaranth_stream import Signature, LastOnTimeout

sig = Signature(32, has_first_last=True)

# Force packet end after 1000 idle cycles
timeout = LastOnTimeout(sig, timeout=1000)
```

---

### Arbitration

*Module: `amaranth_stream.arbiter`*

Packet-aware arbitration components that maintain grant across packet boundaries.

#### StreamArbiter

```python
class StreamArbiter(wiring.Component)
```

Packet-aware N:1 arbiter. Holds grant until `last` to ensure complete packets are forwarded without interleaving.

**Constructor:**

```python
StreamArbiter(
    signature,               # Signature — stream signature (must have has_first_last=True)
    n,                       # int — number of input streams (≥ 1)
    *,
    round_robin=True,        # bool — round-robin or priority arbitration
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature. Must have `has_first_last=True`. |
| `n` | `int` | *(required)* | Number of input streams. Must be ≥ 1. |
| `round_robin` | `bool` | `True` | If `True`, use round-robin arbitration. If `False`, use priority (lower index = higher priority). |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream__0` .. `i_stream__N-1` | `In(signature)` | Input streams |
| `o_stream` | `Out(signature)` | Output stream |
| `grant` | `Out(range(n))` | Currently granted input index |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `n` | `int` | Number of input streams |
| `round_robin` | `bool` | Whether round-robin arbitration is used |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `get_input(i)` | `Interface` | Return the i-th input stream interface |

**Behavior:**

1. When unlocked, selects the next input based on arbitration policy (round-robin or priority).
2. On `first` (without `last`), locks the grant to the current input.
3. While locked, only the granted input can transfer.
4. On `last`, unlocks the grant for the next arbitration decision.
5. Single-beat packets (`first=1, last=1`) don't lock.

**Example:**

```python
from amaranth_stream import Signature, StreamArbiter

sig = Signature(32, has_first_last=True)

# Round-robin arbiter with 4 inputs
arb = StreamArbiter(sig, n=4, round_robin=True)

# Priority arbiter (input 0 has highest priority)
arb_prio = StreamArbiter(sig, n=4, round_robin=False)
```

---

#### StreamDispatcher

```python
class StreamDispatcher(wiring.Component)
```

Packet-aware 1:N dispatcher. Latches `sel` on `first`, holds until `last` to ensure complete packets go to the same output.

**Constructor:**

```python
StreamDispatcher(
    signature,               # Signature — stream signature (must have has_first_last=True)
    n,                       # int — number of output streams (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature. Must have `has_first_last=True`. |
| `n` | `int` | Number of output streams. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream__0` .. `o_stream__N-1` | `Out(signature)` | Output streams |
| `sel` | `In(range(n))` | Selects which output receives the input data. Latched on first beat. |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `n` | `int` | Number of output streams |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `get_output(i)` | `Interface` | Return the i-th output stream interface |

**Behavior:**

1. When unlocked, uses the current `sel` value to route data.
2. On `first` (without `last`), latches `sel` and locks.
3. While locked, uses the latched `sel` regardless of the current `sel` input.
4. On `last`, unlocks for the next packet.

**Example:**

```python
from amaranth_stream import Signature, StreamDispatcher

sig = Signature(32, has_first_last=True)
disp = StreamDispatcher(sig, n=4)

# Route based on header field:
# m.d.comb += disp.sel.eq(header_type)
```

---

### Data Transformation

*Module: `amaranth_stream.transform`*

Components for transforming stream payloads.

#### StreamMap

```python
class StreamMap(wiring.Component)
```

Combinational payload transformation via user-provided function. The transform function is called during `elaborate()` to create combinational logic.

**Constructor:**

```python
StreamMap(
    i_signature,             # Signature — input stream signature
    o_signature,             # Signature — output stream signature
    transform,               # callable — transform(m, payload_in) → payload expression
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input stream signature |
| `o_signature` | `Signature` | Output stream signature |
| `transform` | callable | `transform(m, payload_in)` → payload expression for output. Called during `elaborate()`. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(i_signature)` | Input stream |
| `o_stream` | `Out(o_signature)` | Output stream with transformed payload |

**Behavior:** Applies the user-provided transform function to the input payload combinationally. Passes through valid/ready/first/last/param/keep unchanged (when present on both sides).

**Example:**

```python
from amaranth_stream import Signature, StreamMap

i_sig = Signature(8)
o_sig = Signature(8)

# Double the payload value
mapper = StreamMap(i_sig, o_sig, lambda m, p: p << 1)

# More complex transform with intermediate signals
def my_transform(m, payload):
    result = Signal(8)
    m.d.comb += result.eq(payload ^ 0xFF)  # Bitwise invert
    return result

mapper2 = StreamMap(i_sig, o_sig, my_transform)
```

---

#### StreamFilter

```python
class StreamFilter(wiring.Component)
```

Conditional beat dropping via user-provided predicate. Beats where the predicate returns 0 are consumed but not forwarded.

**Constructor:**

```python
StreamFilter(
    signature,               # Signature — stream signature for both ports
    predicate,               # callable — predicate(m, payload) → Signal(1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature for both input and output ports |
| `predicate` | callable | `predicate(m, payload)` → `Signal(1)`. Returns 1 to pass, 0 to drop. Called during `elaborate()`. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream (dropped beats are consumed but not forwarded) |

**Behavior:**

- When predicate returns 1: `o_stream.valid = i_stream.valid`, `i_stream.ready = o_stream.ready` (normal pass-through)
- When predicate returns 0: `o_stream.valid = 0`, `i_stream.ready = 1` (beat consumed and dropped)

**Example:**

```python
from amaranth_stream import Signature, StreamFilter

sig = Signature(8)

# Only pass even values
filt = StreamFilter(sig, lambda m, p: ~p[0])

# Only pass non-zero values
filt2 = StreamFilter(sig, lambda m, p: p.any())
```

---

#### EndianSwap

```python
class EndianSwap(wiring.Component)
```

Byte-order reversal. Payload must be a multiple of 8 bits.

**Constructor:**

```python
EndianSwap(signature)  # Signature — stream signature (payload width must be multiple of 8)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature. Payload width must be a multiple of 8. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream with reversed byte order |

**Raises:** `ValueError` if payload width is not a multiple of 8.

**Behavior:** Reverses the byte order of the payload. For a 32-bit payload `[B0, B1, B2, B3]`, the output is `[B3, B2, B1, B0]`. All other signals pass through unchanged.

**Example:**

```python
from amaranth_stream import Signature, EndianSwap

sig = Signature(32, has_first_last=True)
swap = EndianSwap(sig)
# Input:  0xDEADBEEF → Output: 0xEFBEADDE
```

---

#### ByteAligner

```python
class ByteAligner(wiring.Component)
```

Sub-word byte alignment with configurable shift. Shifts the payload left by a runtime-configurable number of bytes.

**Constructor:**

```python
ByteAligner(
    signature,               # Signature — stream signature
    max_shift,               # int — maximum shift in bytes (≥ 1)
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature |
| `max_shift` | `int` | Maximum shift in bytes. Must be ≥ 1. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream with shifted payload |
| `shift` | `In(range(max_shift + 1))` | Number of bytes to shift left |

**Behavior:** Implements a barrel shifter: `output_payload = input_payload << (shift × 8)`. All other signals pass through unchanged.

**Example:**

```python
from amaranth_stream import Signature, ByteAligner

sig = Signature(32)
aligner = ByteAligner(sig, max_shift=3)
# shift=0: no change
# shift=1: payload shifted left by 8 bits
# shift=2: payload shifted left by 16 bits
```

---

#### GranularEndianSwap

```python
class GranularEndianSwap(wiring.Component)
```

Per-chunk byte-order reversal for multi-DWORD streams. Unlike `EndianSwap` which reverses all bytes across the full data width, this component reverses bytes independently within each `chunk_size`-bit chunk. This is required by PCIe and many protocols that need per-DWORD (32-bit) independent byte reversal.

**Constructor:**

```python
GranularEndianSwap(
    data_width,              # int — total data width in bits
    chunk_size=32,           # int — size of each chunk in bits (default 32 for DWORD)
    *,
    field="dat",             # str — which payload field to swap
    be_mode=False,           # bool — also reverse keep bits within each chunk
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_width` | `int` | *(required)* | Total data width in bits. Must be a multiple of `chunk_size`. |
| `chunk_size` | `int` | `32` | Size of each chunk in bits. Must be a multiple of 8. |
| `field` | `str` | `"dat"` | Which payload field to swap. Currently only `"dat"` (payload) is supported. |
| `be_mode` | `bool` | `False` | When `True`, also reverse the byte-enable (`keep`) bits within each chunk. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream with per-chunk reversed byte order |

**Example:**

```python
from amaranth_stream import GranularEndianSwap

# Per-DWORD byte swap on 128-bit data (4 DWORDs, each independently reversed)
swap = GranularEndianSwap(128, chunk_size=32)
# Input:  [D0B0,D0B1,D0B2,D0B3, D1B0,D1B1,D1B2,D1B3, ...]
# Output: [D0B3,D0B2,D0B1,D0B0, D1B3,D1B2,D1B1,D1B0, ...]
```

---

#### PacketAligner

```python
class PacketAligner(wiring.Component)
```

Cross-beat packet realignment for wide data buses. Many protocols (e.g. PCIe PHY RX) deliver packets that start at a non-zero offset within a wide data word. This component stitches data across beat boundaries so that the output packet is aligned to offset 0.

**Constructor:**

```python
PacketAligner(
    data_width,              # int — total data width in bits (e.g. 128)
    granularity=32,          # int — alignment granularity in bits (default 32 for DWORD)
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_width` | `int` | *(required)* | Total data width in bits. Must be a multiple of `granularity`. |
| `granularity` | `int` | `32` | Alignment granularity in bits. `data_width` must be ≥ `granularity`. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(Signature(data_width, has_first_last=True))` | Input stream |
| `o_stream` | `Out(Signature(data_width, has_first_last=True))` | Output stream with realigned payload |
| `offset` | `In(range(n_lanes))` | Starting offset in granularity units. Sampled when `first=1` on input. |

**Behavior:** Uses an FSM with IDLE, PASS, ALIGN, and FLUSH states. When offset is 0, passes through directly. When offset is non-zero, absorbs the first beat into a carry register, then stitches carry with subsequent beats using a barrel shifter. A flush beat emits remaining carry data at packet end.

**Example:**

```python
from amaranth_stream import PacketAligner

# 128-bit data bus with DWORD alignment
aligner = PacketAligner(128, granularity=32)
# offset=2: packet starts at DWORD 2 of the first beat
# The aligner shifts data so output starts at DWORD 0
```

---

#### WordReorder

```python
class WordReorder(wiring.Component)
```

Reorder words within a data beat according to a fixed permutation. Useful for reversing DWORDs in a wide data word or performing arbitrary word-level shuffles.

**Constructor:**

```python
WordReorder(
    data_width,              # int — total data width in bits (e.g. 256)
    word_width=32,           # int — width of each word in bits (default 32 for DWORD)
    *,
    order,                   # tuple of int — reorder pattern
    field="dat",             # str — which field to reorder
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_width` | `int` | *(required)* | Total data width in bits. Must be a multiple of `word_width`. |
| `word_width` | `int` | `32` | Width of each word in bits. |
| `order` | `tuple` of `int` | *(required)* | Reorder pattern. `order[i]` specifies which input word index supplies output word `i`. Length must equal `data_width // word_width`. |
| `field` | `str` | `"dat"` | Which field to reorder. Currently only `"dat"` (payload) is supported. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream |
| `o_stream` | `Out(signature)` | Output stream with reordered words |

**Behavior:** Applies the permutation to both payload words and corresponding keep bits. All other signals pass through unchanged.

**Example:**

```python
from amaranth_stream import WordReorder

# Reverse 8 DWORDs in a 256-bit word
reorder = WordReorder(256, word_width=32, order=(7, 6, 5, 4, 3, 2, 1, 0))

# Swap pairs of DWORDs in a 128-bit word
swap_pairs = WordReorder(128, word_width=32, order=(1, 0, 3, 2))
```

---

### Monitoring & Debug

*Module: `amaranth_stream.monitor`*

Components for monitoring stream performance and checking protocol compliance.

#### StreamMonitor

```python
class StreamMonitor(wiring.Component)
```

Performance counters: transfers, stalls, idles, packets. Tap-through — passes all signals from `i_stream` to `o_stream` unchanged while counting events.

**Constructor:**

```python
StreamMonitor(
    signature,               # Signature — stream signature
    counter_width=32,        # int — width of performance counters
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature for both input and output ports |
| `counter_width` | `int` | `32` | Width of the performance counters in bits |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(signature)` | Input stream (tap-through to o_stream) |
| `o_stream` | `Out(signature)` | Output stream (identical to i_stream) |
| `transfer_count` | `Out(counter_width)` | Number of completed transfers (`valid & ready`) |
| `stall_count` | `Out(counter_width)` | Number of stall cycles (`valid & ~ready`) |
| `idle_count` | `Out(counter_width)` | Number of idle cycles (`~valid & ready`) |
| `packet_count` | `Out(counter_width)` | Number of completed packets (`valid & ready & last`) |
| `clear` | `In(1)` | Reset all counters to 0 |

**Behavior:**

| Event | Condition | Counter |
|-------|-----------|---------|
| Transfer | `valid & ready` | `transfer_count` |
| Stall | `valid & ~ready` | `stall_count` |
| Idle | `~valid & ready` | `idle_count` |
| Packet | `valid & ready & last` | `packet_count` (only if `has_first_last`) |

**Example:**

```python
from amaranth_stream import Signature, StreamMonitor

sig = Signature(32, has_first_last=True)
mon = StreamMonitor(sig, counter_width=16)

# Insert into pipeline:
# source → mon.i_stream, mon.o_stream → sink
# Read counters: mon.transfer_count, mon.stall_count, etc.
# Clear counters: m.d.comb += mon.clear.eq(clear_signal)
```

---

#### StreamChecker

```python
class StreamChecker(wiring.Component)
```

Protocol assertion checker for simulation. Monitors a stream for protocol violations. This is a passive tap — it does NOT drive `ready`.

**Constructor:**

```python
StreamChecker(signature)  # Signature — stream signature
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `stream` | `In(signature)` | Stream to monitor (tap-only, does NOT drive ready) |
| `error` | `Out(1)` | Set to 1 (sticky) if any protocol violation is detected |

**Checked Rules:**

1. **Valid persistence:** Once `valid` is asserted, it must not deassert until a transfer occurs.
2. **Payload stability:** Once `valid` is asserted, `payload` must not change until transfer.
3. **First/last stability:** If `has_first_last`, `first` and `last` must not change while `valid & ~ready`.

**Behavior:** The `error` output is sticky — once set, it remains high until reset. Previous cycle values are compared against current values to detect violations.

**Example:**

```python
from amaranth_stream import Signature, StreamChecker

sig = Signature(32, has_first_last=True)
checker = StreamChecker(sig)

# In testbench:
# assert not ctx.get(checker.error), "Stream protocol violation!"
```

---

#### StreamProtocolChecker

```python
class StreamProtocolChecker(wiring.Component)
```

Protocol checker with error codes for stream protocol violations. Passively monitors a stream and reports protocol violations with specific error codes. The checker does not drive `ready` or `valid` — it is purely an observer.

**Constructor:**

```python
StreamProtocolChecker(
    signature,               # Signature — stream signature
    domain="sync",           # str — clock domain (default "sync")
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature to monitor |
| `domain` | `str` | `"sync"` | Clock domain |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `stream` | `In(signature)` | Stream to monitor (passive — does NOT drive ready) |
| `error` | `Out(1)` | Asserted when a protocol violation is detected this cycle |
| `error_code` | `Out(2)` | Indicates which violation occurred (0–3) |

**Error Codes:**

| Code | Description |
|------|-------------|
| 0 | No error |
| 1 | `first` without preceding `last` |
| 2 | `valid` deasserted without handshake |
| 3 | `payload` changed without handshake |

**Behavior:** Unlike `StreamChecker` (which has a sticky error flag), `StreamProtocolChecker` reports errors on a per-cycle basis with specific error codes. It checks valid persistence, payload stability, and first/last sequencing.

**Example:**

```python
from amaranth_stream import Signature, StreamProtocolChecker

sig = Signature(32, has_first_last=True)
checker = StreamProtocolChecker(sig)

# In testbench:
# error = ctx.get(checker.error)
# code = ctx.get(checker.error_code)
# if error:
#     print(f"Protocol violation! Code: {code}")
```

---

### AXI-Stream Bridge

*Module: `amaranth_stream.axi_stream`*

Components for bridging between AXI-Stream and amaranth_stream protocols.

#### AXIStreamSignature

```python
class AXIStreamSignature(wiring.Signature)
```

AXI-Stream interface definition following the ARM AMBA AXI-Stream specification.

**Constructor:**

```python
AXIStreamSignature(
    data_width,              # int — TDATA width in bits (must be multiple of 8)
    *,
    id_width=0,              # int — TID width (0 to omit)
    dest_width=0,            # int — TDEST width (0 to omit)
    user_width=0,            # int — TUSER width (0 to omit)
    has_tfirst=False,        # bool — include TFIRST signal
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_width` | `int` | *(required)* | TDATA width in bits. Must be a multiple of 8. |
| `id_width` | `int` | `0` | TID width. 0 to omit. |
| `dest_width` | `int` | `0` | TDEST width. 0 to omit. |
| `user_width` | `int` | `0` | TUSER width. 0 to omit. |
| `has_tfirst` | `bool` | `False` | If `True`, include a `tfirst` member signal. |

**Members:**

| Member | Direction | Shape | Condition |
|--------|-----------|-------|-----------|
| `tdata` | `Out` | `data_width` | Always |
| `tvalid` | `Out` | 1 | Always |
| `tready` | `In` | 1 | Always |
| `tkeep` | `Out` | `data_width // 8` | Always |
| `tstrb` | `Out` | `data_width // 8` | Always |
| `tlast` | `Out` | 1 | Always |
| `tfirst` | `Out` | 1 | `has_tfirst=True` |
| `tid` | `Out` | `id_width` | `id_width > 0` |
| `tdest` | `Out` | `dest_width` | `dest_width > 0` |
| `tuser` | `Out` | `user_width` | `user_width > 0` |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `data_width` | `int` | TDATA width |
| `id_width` | `int` | TID width |
| `dest_width` | `int` | TDEST width |
| `user_width` | `int` | TUSER width |
| `has_tfirst` | `bool` | Whether TFIRST is included |

**Example:**

```python
from amaranth_stream import AXIStreamSignature

# 32-bit AXI-Stream with TID
axi_sig = AXIStreamSignature(32, id_width=4)
print(axi_sig)
# AXIStreamSignature(32, id_width=4)
```

---

#### AXIStreamToStream

```python
class AXIStreamToStream(wiring.Component)
```

AXI-Stream → amaranth_stream bridge. Converts AXI-Stream signals to the amaranth_stream protocol.

**Constructor:**

```python
AXIStreamToStream(
    axi_signature,           # AXIStreamSignature — AXI-Stream interface signature
    stream_signature,        # Signature — output stream signature
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `axi_signature` | `AXIStreamSignature` | AXI-Stream interface signature |
| `stream_signature` | `Signature` | Output stream signature. Should have `has_first_last=True` and `has_keep=True` for full mapping. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `axi` | `In(axi_signature)` | AXI-Stream input |
| `o_stream` | `Out(stream_signature)` | amaranth_stream output |

**Signal Mapping:**

| AXI-Stream | amaranth_stream | Notes |
|------------|----------------|-------|
| `tdata` | `payload` | Direct mapping |
| `tvalid` | `valid` | Direct mapping |
| `tready` | `ready` | Direct mapping |
| `tlast` | `last` | If `has_first_last` |
| — | `first` | Generated: tracks first beat after reset/last |
| `tkeep` | `keep` | If `has_keep` |

**Example:**

```python
from amaranth_stream import Signature, AXIStreamSignature, AXIStreamToStream

axi_sig = AXIStreamSignature(32)
stream_sig = Signature(32, has_first_last=True, has_keep=True)

bridge = AXIStreamToStream(axi_sig, stream_sig)
# bridge.axi.tdata → bridge.o_stream.payload
```

---

#### StreamToAXIStream

```python
class StreamToAXIStream(wiring.Component)
```

amaranth_stream → AXI-Stream bridge. Converts amaranth_stream signals to the AXI-Stream protocol.

**Constructor:**

```python
StreamToAXIStream(
    stream_signature,        # Signature — input stream signature
    axi_signature,           # AXIStreamSignature — AXI-Stream output signature
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `stream_signature` | `Signature` | Input stream signature |
| `axi_signature` | `AXIStreamSignature` | AXI-Stream output signature |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `i_stream` | `In(stream_signature)` | amaranth_stream input |
| `axi` | `Out(axi_signature)` | AXI-Stream output |

**Signal Mapping:**

| amaranth_stream | AXI-Stream | Notes |
|----------------|------------|-------|
| `payload` | `tdata` | Direct mapping |
| `valid` | `tvalid` | Direct mapping |
| `ready` | `tready` | Direct mapping |
| `last` | `tlast` | If `has_first_last` |
| `keep` | `tkeep` | If `has_keep`; otherwise all-ones |
| `keep` | `tstrb` | Same as `tkeep`; otherwise all-ones |

**Example:**

```python
from amaranth_stream import Signature, AXIStreamSignature, StreamToAXIStream

stream_sig = Signature(64, has_first_last=True, has_keep=True)
axi_sig = AXIStreamSignature(64)

bridge = StreamToAXIStream(stream_sig, axi_sig)
# bridge.i_stream.payload → bridge.axi.tdata
```

---

### SOP/EOP Adapter

*Module: `amaranth_stream.adapter`*

Components for bridging between SOP/EOP/valid-mask framing (common in FPGA hard IP such as Gowin PCIe, Xilinx Aurora, Intel Avalon-ST) and amaranth-stream's valid/ready/first/last framing.

#### SOPEOPAdapter

```python
class SOPEOPAdapter(wiring.Component)
```

Convert SOP/EOP/valid-mask framing to amaranth-stream. Bridges from FPGA hard IP interfaces to amaranth-stream's valid/ready/first/last protocol.

**Constructor:**

```python
SOPEOPAdapter(
    data_width,              # int — data bus width in bits (multiple of 32)
    *,
    granularity="byte",      # str — valid-mask granularity: "bit", "byte", or "dword"
    dword_reorder=False,     # bool — reverse DWORD order within the data word
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_width` | `int` | *(required)* | Width of the data bus in bits. Must be a multiple of 32. |
| `granularity` | `str` | `"byte"` | Valid-mask granularity: `"bit"`, `"byte"`, or `"dword"`. |
| `dword_reorder` | `bool` | `False` | When `True`, reverses DWORD order within the data word. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `sink` | `In(SOPEOPSignature)` | SOP/EOP input from hard IP (data, sop, eop, valid_mask, valid, ready) |
| `source` | `Out(StreamSignature)` | amaranth-stream output with `first`, `last`, and `keep` |

**Signal Mapping:**

| SOP/EOP | amaranth_stream | Notes |
|---------|----------------|-------|
| `data` | `payload` | Direct mapping (or DWORD-reordered) |
| `sop` | `first` | Direct mapping |
| `eop` | `last` | Direct mapping |
| `valid_mask` | `keep` | Expanded from granularity to byte-level |
| `valid` | `valid` | Direct mapping |
| `ready` | `ready` | Direct mapping |

**Example:**

```python
from amaranth_stream import SOPEOPAdapter

# 256-bit data bus with byte-level valid mask
adapter = SOPEOPAdapter(256, granularity="byte")

# With DWORD reordering (e.g. for Gowin PCIe)
adapter_reorder = SOPEOPAdapter(256, granularity="dword", dword_reorder=True)
```

---

#### StreamToSOPEOP

```python
class StreamToSOPEOP(wiring.Component)
```

Convert amaranth-stream to SOP/EOP/valid-mask framing. Bridges from amaranth-stream's valid/ready/first/last protocol to FPGA hard IP interfaces.

**Constructor:**

```python
StreamToSOPEOP(
    data_width,              # int — data bus width in bits (multiple of 32)
    *,
    granularity="byte",      # str — valid-mask granularity: "bit", "byte", or "dword"
    dword_reorder=False,     # bool — reverse DWORD order within the data word
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_width` | `int` | *(required)* | Width of the data bus in bits. Must be a multiple of 32. |
| `granularity` | `str` | `"byte"` | Valid-mask granularity: `"bit"`, `"byte"`, or `"dword"`. |
| `dword_reorder` | `bool` | `False` | When `True`, reverses DWORD order within the data word. |

**Ports:**

| Port | Direction | Description |
|------|-----------|-------------|
| `sink` | `In(StreamSignature)` | amaranth-stream input with `first`, `last`, and `keep` |
| `source` | `Out(SOPEOPSignature)` | SOP/EOP output to hard IP |

**Example:**

```python
from amaranth_stream import StreamToSOPEOP

# 256-bit data bus with byte-level valid mask
bridge = StreamToSOPEOP(256, granularity="byte")

# With DWORD reordering
bridge_reorder = StreamToSOPEOP(256, granularity="dword", dword_reorder=True)
```

---

## Testing

The library includes comprehensive tests for all components. Run them with PDM:

```bash
# Run all tests
pdm run pytest tests/ -v

# Run tests for a specific module
pdm run pytest tests/test_base.py -v
pdm run pytest tests/test_sim.py -v
pdm run pytest tests/test_buffer.py -v
pdm run pytest tests/test_fifo.py -v
pdm run pytest tests/test_converter.py -v
pdm run pytest tests/test_routing.py -v
pdm run pytest tests/test_packet.py -v
pdm run pytest tests/test_arbiter.py -v
pdm run pytest tests/test_pipeline.py -v
pdm run pytest tests/test_transform.py -v
pdm run pytest tests/test_monitor.py -v
pdm run pytest tests/test_axi_stream.py -v
pdm run pytest tests/test_adapter.py -v
pdm run pytest tests/test_integration.py -v

# Run with verbose output and stop on first failure
pdm run pytest tests/ -v -x

# Run a specific test
pdm run pytest tests/test_buffer.py::TestBuffer::test_pipe_valid -v
```

### Test Coverage

| Test Module | Components Tested |
|-------------|-------------------|
| `test_base.py` | `Signature`, `Interface`, `core_to_extended` |
| `test_sim.py` | `StreamSimSender`, `StreamSimReceiver` |
| `test_buffer.py` | `Buffer`, `PipeValid`, `PipeReady`, `Delay` |
| `test_fifo.py` | `StreamFIFO`, `StreamAsyncFIFO` |
| `test_converter.py` | `StreamConverter`, `StrideConverter`, `Gearbox`, `StreamCast`, `Pack`, `Unpack` |
| `test_routing.py` | `StreamMux`, `StreamDemux`, `StreamGate`, `StreamSplitter`, `StreamJoiner` |
| `test_packet.py` | `HeaderLayout`, `Packetizer`, `Depacketizer`, `PacketFIFO`, `PacketStatus`, `Stitcher`, `LastInserter`, `LastOnTimeout` |
| `test_arbiter.py` | `StreamArbiter`, `StreamDispatcher` |
| `test_pipeline.py` | `Pipeline`, `BufferizeEndpoints` |
| `test_transform.py` | `StreamMap`, `StreamFilter`, `EndianSwap`, `GranularEndianSwap`, `ByteAligner`, `PacketAligner`, `WordReorder` |
| `test_monitor.py` | `StreamMonitor`, `StreamChecker`, `StreamProtocolChecker` |
| `test_axi_stream.py` | `AXIStreamSignature`, `AXIStreamToStream`, `StreamToAXIStream` |
| `test_adapter.py` | `SOPEOPAdapter`, `StreamToSOPEOP` |
| `test_integration.py` | End-to-end pipeline integration tests |

---

## Architecture Notes

### Design Philosophy

1. **Parallel hierarchy:** Amaranth's built-in `amaranth.lib.stream.Signature` is `@final` and cannot be subclassed. This library implements a parallel `Signature`/`Interface` hierarchy that extends the core protocol with optional signals.

2. **Wiring-based composition:** All components use Amaranth's `wiring.Component` base class with explicit `In`/`Out` port declarations. This enables type-safe connections via `wiring.connect()`.

3. **Signal packing for FIFOs:** Stream FIFOs pack all forward signals (payload, first, last, param, keep) into a single wide data word for storage. This allows using Amaranth's built-in FIFO primitives (which only support a single data word) while preserving all stream metadata.

4. **Packet awareness:** Components that deal with packet boundaries (arbiter, dispatcher, packet FIFO) use `first`/`last` signals to maintain atomicity — they never interleave beats from different packets.

### Stream Signal Directions

From the **source** (initiator) perspective:

```
Source drives:  payload (Out), valid (Out), first (Out), last (Out), param (Out), keep (Out)
Sink drives:    ready (In)
```

From the **sink** (responder) perspective (flipped):

```
Sink sees:      payload (In), valid (In), first (In), last (In), param (In), keep (In)
Sink drives:    ready (Out)
```

### Forward vs. Backward Signals

| Category | Signals | Direction | Registered by |
|----------|---------|-----------|---------------|
| Forward | `payload`, `valid`, `first`, `last`, `param`, `keep` | Source → Sink | `PipeValid` / `Buffer(pipe_valid=True)` |
| Backward | `ready` | Sink → Source | `PipeReady` / `Buffer(pipe_ready=True)` |

### Component Naming Conventions

| Prefix/Suffix | Meaning |
|---------------|---------|
| `Stream*` | Operates on stream interfaces |
| `*FIFO` | Contains FIFO storage |
| `*CDC` | Clock-domain crossing |
| `Pipe*` | Pipeline register variant |
| `*Signature` | Defines an interface signature |
| `*Sim*` | Simulation-only (BFM) |

### Import Structure

All 52 components are re-exported from the top-level `amaranth_stream` package:

```python
# Import everything
from amaranth_stream import *

# Or import specific components
from amaranth_stream import Signature, Buffer, StreamFIFO, Pipeline
```

---

## Component Summary Table

| # | Component | Module | Category | Description |
|---|-----------|--------|----------|-------------|
| 1 | `Signature` | `_base` | Core | Extended stream signature with optional first/last, param, keep |
| 2 | `Interface` | `_base` | Core | Concrete stream interface from a Signature |
| 3 | `core_to_extended` | `_base` | Core | Convert core Amaranth stream signature to extended |
| 4 | `connect_streams` | `_base` | Core | Connect two stream interfaces combinationally |
| 5 | `StreamSimSender` | `sim` | Sim BFM | Testbench BFM: drives stream source |
| 6 | `StreamSimReceiver` | `sim` | Sim BFM | Testbench BFM: consumes stream sink |
| 7 | `Buffer` | `buffer` | Buffering | Pipeline register (configurable forward/backward) |
| 8 | `PipeValid` | `buffer` | Buffering | Forward-registered pipeline stage |
| 9 | `PipeReady` | `buffer` | Buffering | Backward-registered pipeline stage |
| 10 | `Delay` | `buffer` | Buffering | N-stage pipeline delay |
| 11 | `Pipeline` | `pipeline` | Pipeline | Declarative pipeline builder |
| 12 | `BufferizeEndpoints` | `pipeline` | Pipeline | Wrap component with buffers on all stream ports |
| 13 | `StreamFIFO` | `fifo` | FIFO | Synchronous FIFO with stream interfaces |
| 14 | `StreamAsyncFIFO` | `fifo` | FIFO | Asynchronous (cross-domain) FIFO |
| 15 | `StreamCDC` | `cdc` | CDC | Automatic clock-domain crossing |
| 16 | `StreamConverter` | `converter` | Width Conv. | Integer-ratio width converter |
| 17 | `StrideConverter` | `converter` | Width Conv. | Non-integer ratio width converter (LCM) |
| 18 | `Gearbox` | `converter` | Width Conv. | Shift-register width converter |
| 19 | `StreamCast` | `converter` | Width Conv. | Zero-cost bit reinterpretation |
| 20 | `Pack` | `converter` | Width Conv. | N narrow → 1 wide beat |
| 21 | `Unpack` | `converter` | Width Conv. | 1 wide → N narrow beats |
| 22 | `ByteEnableSerializer` | `converter` | Width Conv. | Serialize wide stream with byte enables to narrow stream |
| 23 | `StreamMux` | `routing` | Routing | N:1 multiplexer |
| 24 | `StreamDemux` | `routing` | Routing | 1:N demultiplexer |
| 25 | `StreamGate` | `routing` | Routing | Enable/disable gate |
| 26 | `StreamSplitter` | `routing` | Routing | 1:N synchronized broadcast |
| 27 | `StreamJoiner` | `routing` | Routing | N:1 round-robin join |
| 28 | `HeaderLayout` | `packet` | Packet | Declarative header definition |
| 29 | `Packetizer` | `packet` | Packet | Insert header before payload |
| 30 | `Depacketizer` | `packet` | Packet | Extract header, strip header beats |
| 31 | `PacketFIFO` | `packet` | Packet | Atomic packet FIFO |
| 32 | `PacketStatus` | `packet` | Packet | Packet boundary tracker (tap-only) |
| 33 | `Stitcher` | `packet` | Packet | Group N packets into one |
| 34 | `LastInserter` | `packet` | Packet | Fixed-size packet creation |
| 35 | `LastOnTimeout` | `packet` | Packet | Timeout-based packet termination |
| 36 | `StreamArbiter` | `arbiter` | Arbitration | Packet-aware N:1 arbiter |
| 37 | `StreamDispatcher` | `arbiter` | Arbitration | Packet-aware 1:N dispatcher |
| 38 | `StreamMap` | `transform` | Transform | Combinational payload transformation |
| 39 | `StreamFilter` | `transform` | Transform | Conditional beat dropping |
| 40 | `EndianSwap` | `transform` | Transform | Byte-order reversal |
| 41 | `GranularEndianSwap` | `transform` | Transform | Per-chunk byte-order reversal |
| 42 | `ByteAligner` | `transform` | Transform | Sub-word byte alignment |
| 43 | `PacketAligner` | `transform` | Transform | Cross-beat packet realignment |
| 44 | `WordReorder` | `transform` | Transform | Fixed-permutation word reorder |
| 45 | `StreamMonitor` | `monitor` | Debug | Performance counters (tap-through) |
| 46 | `StreamChecker` | `monitor` | Debug | Protocol assertion checker (sticky) |
| 47 | `StreamProtocolChecker` | `monitor` | Debug | Protocol checker with error codes |
| 48 | `AXIStreamSignature` | `axi_stream` | AXI Bridge | AXI-Stream interface definition |
| 49 | `AXIStreamToStream` | `axi_stream` | AXI Bridge | AXI-Stream → amaranth_stream |
| 50 | `StreamToAXIStream` | `axi_stream` | AXI Bridge | amaranth_stream → AXI-Stream |
| 51 | `SOPEOPAdapter` | `adapter` | SOP/EOP | SOP/EOP → amaranth_stream bridge |
| 52 | `StreamToSOPEOP` | `adapter` | SOP/EOP | amaranth_stream → SOP/EOP bridge |

---

## License

BSD-2-Clause. See [LICENSE.txt](LICENSE.txt) for details.
