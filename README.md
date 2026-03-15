# amaranth-stream

A comprehensive stream processing library for [Amaranth HDL](https://amaranth-lang.org/) providing 44 public components for building high-performance streaming data pipelines in digital hardware.

**amaranth-stream** extends Amaranth's built-in stream primitives with optional packet framing (`first`/`last`), sideband parameters (`param`), byte-enable masks (`keep`), and a rich set of components for buffering, width conversion, routing, packet processing, arbitration, data transformation, monitoring, and AXI-Stream bridging.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Stream Protocol](#stream-protocol)
- [API Reference](#api-reference)
  - [Core](#core)
  - [Simulation BFMs](#simulation-bfms)
  - [Buffering & Pipeline](#buffering--pipeline)
  - [FIFOs & CDC](#fifos--cdc)
  - [Width Conversion](#width-conversion)
  - [Routing](#routing)
  - [Packet Processing](#packet-processing)
  - [Arbitration](#arbitration)
  - [Data Transformation](#data-transformation)
  - [Monitoring & Debug](#monitoring--debug)
  - [AXI-Stream Bridge](#axi-stream-bridge)
- [Testing](#testing)
- [Architecture](#architecture)

---

## Installation

amaranth-stream uses [PDM](https://pdm-project.org/) as its build system.

```bash
# Clone the repository
git clone <repo-url>
cd amaranth-stream

# Install with PDM (includes Amaranth as a dev dependency)
pdm install

# Verify installation
pdm run python -c "import amaranth_stream; print('OK')"
```

### Requirements

- Python ≥ 3.9
- Amaranth HDL (installed automatically as a dev dependency via editable local path)

---

## Quick Start

### 1. Create a Stream Signature

```python
from amaranth_stream import Signature

# Basic 8-bit stream
sig = Signature(8)

# 32-bit stream with packet framing and byte enables
pkt_sig = Signature(32, has_first_last=True, has_keep=True)

# Stream with sideband parameter
param_sig = Signature(16, param_shape=4)
```

### 2. Use a Buffer Component

```python
from amaranth import *
from amaranth.lib.wiring import connect
from amaranth_stream import Signature, Buffer

class MyDesign(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        sig = Signature(8, has_first_last=True)
        buf = Buffer(sig)
        m.submodules.buf = buf

        # Connect your logic to buf.i_stream and buf.o_stream
        return m
```

### 3. Simulate with BFMs

```python
from amaranth import *
from amaranth.sim import Simulator
from amaranth_stream import Signature, Buffer, StreamSimSender, StreamSimReceiver

sig = Signature(8, has_first_last=True)
dut = Buffer(sig)

async def testbench(ctx):
    sender = StreamSimSender(dut.i_stream)
    receiver = StreamSimReceiver(dut.o_stream)

    # Send a single beat
    await sender.send(ctx, 0xAB, first=1, last=1)

    # Receive and verify
    beat = await receiver.recv(ctx)
    assert beat["payload"] == 0xAB

sim = Simulator(dut)
sim.add_clock(1e-6)
sim.add_testbench(testbench)
with sim.write_vcd("test.vcd"):
    sim.run()
```

---

## Stream Protocol

### Handshake

amaranth-stream uses a **valid/ready** handshake protocol:

```
         ┌─────────┐         ┌─────────┐
         │  Source  │──valid──▶│  Sink   │
         │         │──payload─▶│         │
         │         │◀──ready──│         │
         └─────────┘         └─────────┘
```

- **`valid`** (source → sink): The source asserts `valid` when it has data available.
- **`ready`** (sink → source): The sink asserts `ready` when it can accept data.
- **Transfer**: A transfer occurs on a clock edge when **both** `valid` AND `ready` are high.
- **Rule**: Once `valid` is asserted, the source must not change `payload` or deassert `valid` until the transfer completes.

### Optional Signals

| Signal | Direction | Description |
|--------|-----------|-------------|
| `payload` | source → sink | Data word (configurable width) |
| `valid` | source → sink | Data available |
| `ready` | sink → source | Sink can accept |
| `first` | source → sink | First beat of a packet (requires `has_first_last=True`) |
| `last` | source → sink | Last beat of a packet (requires `has_first_last=True`) |
| `param` | source → sink | Sideband parameter (requires `param_shape≠None`) |
| `keep` | source → sink | Byte-enable mask, width = `ceil(payload_width / 8)` (requires `has_keep=True`) |

---

## API Reference

### Core

Defined in [`amaranth_stream/_base.py`](amaranth_stream/_base.py).

#### `Signature`

Extended stream signature with optional `first`/`last`, `param`, and `keep` members. Subclass of `amaranth.lib.wiring.Signature`.

```python
Signature(payload_shape, *, always_valid=False, always_ready=False,
          has_first_last=False, param_shape=None, has_keep=False)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `payload_shape` | `ShapeLike` | *(required)* | Shape of the payload member |
| `always_valid` | `bool` | `False` | Drive `valid` to `Const(1)` in created Interface |
| `always_ready` | `bool` | `False` | Drive `ready` to `Const(1)` in created Interface |
| `has_first_last` | `bool` | `False` | Add `first` and `last` packet framing members |
| `param_shape` | `ShapeLike` or `None` | `None` | Shape of sideband `param` member |
| `has_keep` | `bool` | `False` | Add `keep` byte-enable member |

**Properties:** `payload_shape`, `always_valid`, `always_ready`, `has_first_last`, `param_shape`, `has_keep`, `payload_width`

```python
from amaranth_stream import Signature

# 32-bit stream with packet framing and 4-bit sideband
sig = Signature(32, has_first_last=True, param_shape=4, has_keep=True)
print(sig.payload_width)  # 32
```

---

#### `Interface`

Concrete stream interface created from a `Signature`. Populates signal attributes and optionally replaces `valid`/`ready` with `Const(1)`.

```python
Interface(signature, *, path=None, src_loc_at=0)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | The stream signature to instantiate |

**Attributes:** `signature`, `payload`, `valid`, `ready`, `p` (alias for `payload`), and optionally `first`, `last`, `param`, `keep`.

```python
sig = Signature(8, has_first_last=True)
iface = sig.create()
# iface.payload, iface.valid, iface.ready, iface.first, iface.last
# iface.p is shorthand for iface.payload
```

---

#### `core_to_extended(core_sig)`

Converts an `amaranth.lib.stream.Signature` to an `amaranth_stream.Signature`.

```python
core_to_extended(core_sig)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `core_sig` | `amaranth.lib.stream.Signature` | Core Amaranth stream signature |

**Returns:** `amaranth_stream.Signature` with matching `payload_shape`, `always_valid`, `always_ready`.

```python
from amaranth.lib.stream import Signature as CoreSig
from amaranth_stream import core_to_extended

core = CoreSig(8)
ext = core_to_extended(core)  # amaranth_stream.Signature(8)
```

---

### Simulation BFMs

Defined in [`amaranth_stream/sim.py`](amaranth_stream/sim.py). Bus Functional Models for driving and consuming streams in Amaranth async testbenches.

#### `StreamSimSender`

Drives a stream source (initiator side) in simulation.

```python
StreamSimSender(stream, *, domain="sync", random_valid=False, seed=None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stream` | `Interface` | *(required)* | Stream interface to drive |
| `domain` | `str` | `"sync"` | Clock domain name |
| `random_valid` | `bool` | `False` | Randomly deassert `valid` for stress testing |
| `seed` | `int` or `None` | `None` | RNG seed for reproducible random delays |

**Methods:**

- `await send(ctx, payload, *, first=None, last=None, param=None, keep=None)` — Send a single beat. Waits for handshake.
- `await send_packet(ctx, payloads, *, param=None)` — Send a complete packet with automatic `first`/`last` framing.

```python
sender = StreamSimSender(dut.i_stream, random_valid=True, seed=42)
await sender.send(ctx, 0xFF, first=1, last=0)
await sender.send_packet(ctx, [0x01, 0x02, 0x03])
```

---

#### `StreamSimReceiver`

Consumes a stream sink (responder side) in simulation.

```python
StreamSimReceiver(stream, *, domain="sync", random_ready=False, seed=None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stream` | `Interface` | *(required)* | Stream interface to consume |
| `domain` | `str` | `"sync"` | Clock domain name |
| `random_ready` | `bool` | `False` | Randomly deassert `ready` for stress testing |
| `seed` | `int` or `None` | `None` | RNG seed for reproducible random delays |

**Methods:**

- `await recv(ctx)` → `dict` — Receive a single beat. Returns `{"payload": ..., "first": ..., "last": ..., ...}`.
- `await recv_packet(ctx)` → `list[dict]` — Receive beats until `last=1`.
- `await expect_packet(ctx, expected_payloads)` — Receive a packet and assert payloads match.

```python
receiver = StreamSimReceiver(dut.o_stream)
beat = await receiver.recv(ctx)
assert beat["payload"] == 0xAB

packet = await receiver.recv_packet(ctx)
await receiver.expect_packet(ctx, [0x01, 0x02, 0x03])
```

---

### Buffering & Pipeline

Defined in [`amaranth_stream/buffer.py`](amaranth_stream/buffer.py) and [`amaranth_stream/pipeline.py`](amaranth_stream/pipeline.py).

#### `Buffer`

Pipeline register that breaks combinational paths. Supports independent control of forward (valid/payload) and backward (ready) path registration.

```python
Buffer(signature, pipe_valid=True, pipe_ready=True)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature |
| `pipe_valid` | `bool` | `True` | Register the forward path |
| `pipe_ready` | `bool` | `True` | Register the backward path |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:**
- `pipe_valid=True, pipe_ready=True` — Full skid buffer (chains PipeValid → PipeReady internally)
- `pipe_valid=True, pipe_ready=False` — Forward-registered only
- `pipe_valid=False, pipe_ready=True` — Backward-registered only
- `pipe_valid=False, pipe_ready=False` — Wire-through (no registers)

```python
sig = Signature(8, has_first_last=True)
buf = Buffer(sig)                          # Full buffer
buf_fwd = Buffer(sig, pipe_ready=False)    # Forward only
buf_bwd = Buffer(sig, pipe_valid=False)    # Backward only
```

---

#### `PipeValid`

Convenience wrapper: forward-registered pipeline stage. Registers `payload`, `valid`, `first`, `last`, `param`, `keep`. Ready is combinational pass-through.

```python
PipeValid(signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature |

**Ports:** `i_stream` (In), `o_stream` (Out)

Equivalent to `Buffer(signature, pipe_valid=True, pipe_ready=False)`.

---

#### `PipeReady`

Convenience wrapper: backward-registered pipeline stage. Ready is registered. Forward path is combinational with a bypass register.

```python
PipeReady(signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature |

**Ports:** `i_stream` (In), `o_stream` (Out)

Equivalent to `Buffer(signature, pipe_valid=False, pipe_ready=True)`.

---

#### `Delay`

N-stage pipeline delay using chained `PipeValid` stages.

```python
Delay(signature, stages=1)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature |
| `stages` | `int` | `1` | Number of pipeline stages (0 = wire-through) |

**Ports:** `i_stream` (In), `o_stream` (Out)

```python
sig = Signature(8)
delay = Delay(sig, stages=3)  # 3-cycle latency
```

---

#### `Pipeline`

Declarative pipeline builder. Chains stages by connecting each stage's `o_stream` to the next stage's `i_stream`.

```python
Pipeline(*stages)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `*stages` | `wiring.Component` | Component instances with `i_stream` and `o_stream` ports |

**Ports:** `i_stream` (In, matching first stage), `o_stream` (Out, matching last stage)

```python
from amaranth_stream import Signature, PipeValid, Pipeline

sig = Signature(8, has_first_last=True)
pipe = Pipeline(
    PipeValid(sig),
    PipeValid(sig),
    PipeValid(sig),
)
# pipe.i_stream → stage_0 → stage_1 → stage_2 → pipe.o_stream
```

---

#### `BufferizeEndpoints`

Wraps a component, inserting `Buffer` stages on all stream ports. For each `In` stream port, a Buffer is inserted before the component. For each `Out` stream port, a Buffer is inserted after.

```python
BufferizeEndpoints(component, *, pipe_valid=True, pipe_ready=True)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `component` | `wiring.Component` | *(required)* | Component to wrap |
| `pipe_valid` | `bool` | `True` | Register forward path in buffers |
| `pipe_ready` | `bool` | `True` | Register backward path in buffers |

**Ports:** Same as the wrapped component's stream ports.

```python
sig = Signature(8, has_first_last=True)
core = PipeValid(sig)
buffered = BufferizeEndpoints(core)
# buffered.i_stream → Buffer → core → Buffer → buffered.o_stream
```

---

### FIFOs & CDC

Defined in [`amaranth_stream/fifo.py`](amaranth_stream/fifo.py) and [`amaranth_stream/cdc.py`](amaranth_stream/cdc.py).

#### `StreamFIFO`

Synchronous FIFO with stream interfaces. Packs all stream signals (`payload`, `first`, `last`, `param`, `keep`) into a single wide data word for storage.

```python
StreamFIFO(signature, depth, *, buffered=True)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature |
| `depth` | `int` | *(required)* | FIFO depth in entries (≥0) |
| `buffered` | `bool` | `True` | Use `SyncFIFOBuffered` (block RAM compatible) vs `SyncFIFO` |

**Ports:** `i_stream` (In), `o_stream` (Out), `level` (Out, `range(depth + 1)`)

```python
sig = Signature(32, has_first_last=True)
fifo = StreamFIFO(sig, depth=64)
# fifo.level gives current fill level
```

---

#### `StreamAsyncFIFO`

Asynchronous (cross-domain) FIFO with stream interfaces. Uses `AsyncFIFO` or `AsyncFIFOBuffered` internally.

```python
StreamAsyncFIFO(signature, depth, *, w_domain="write", r_domain="read", buffered=True)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature |
| `depth` | `int` | *(required)* | FIFO depth (rounded to power of 2 for AsyncFIFO) |
| `w_domain` | `str` | `"write"` | Write clock domain |
| `r_domain` | `str` | `"read"` | Read clock domain |
| `buffered` | `bool` | `True` | Use `AsyncFIFOBuffered` vs `AsyncFIFO` |

**Ports:** `i_stream` (In, in `w_domain`), `o_stream` (Out, in `r_domain`)

```python
sig = Signature(8)
async_fifo = StreamAsyncFIFO(sig, depth=16, w_domain="fast", r_domain="slow")
```

---

#### `StreamCDC`

Automatic clock-domain crossing for streams. When `w_domain == r_domain`, uses a simple `Buffer`. When domains differ, uses `StreamAsyncFIFO`.

```python
StreamCDC(signature, *, depth=8, w_domain="sync", r_domain="sync")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature |
| `depth` | `int` | `8` | FIFO depth for cross-domain case |
| `w_domain` | `str` | `"sync"` | Write clock domain |
| `r_domain` | `str` | `"sync"` | Read clock domain |

**Ports:** `i_stream` (In, in `w_domain`), `o_stream` (Out, in `r_domain`)

```python
sig = Signature(32, has_first_last=True)

# Same domain: becomes a simple Buffer
cdc_same = StreamCDC(sig)

# Cross-domain: becomes an AsyncFIFO
cdc_cross = StreamCDC(sig, w_domain="fast", r_domain="slow", depth=16)
```

---

### Width Conversion

Defined in [`amaranth_stream/converter.py`](amaranth_stream/converter.py).

#### `StreamConverter`

Integer-ratio width converter for flat payloads. The wider width must be an exact integer multiple of the narrower width.

```python
StreamConverter(i_signature, o_signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input stream signature |
| `o_signature` | `Signature` | Output stream signature |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:**
- **Identity** (same width): wire-through
- **Upsize** (narrow → wide): collects `ratio` input beats into one output beat
- **Downsize** (wide → narrow): splits one input beat into `ratio` output beats

Preserves `first`/`last` and `keep` when both signatures have them.

```python
sig_8 = Signature(8, has_first_last=True)
sig_32 = Signature(32, has_first_last=True)

upsize = StreamConverter(sig_8, sig_32)    # 4 × 8-bit → 1 × 32-bit
downsize = StreamConverter(sig_32, sig_8)  # 1 × 32-bit → 4 × 8-bit
```

---

#### `StrideConverter`

Structured field-aware width converter. Handles non-integer ratios by padding to LCM. For integer ratios, uses the same logic as `StreamConverter`.

```python
StrideConverter(i_signature, o_signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input stream signature |
| `o_signature` | `Signature` | Output stream signature |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:** Uses an FSM with FILL/DRAIN states. Collects `lcm/i_width` input beats, then outputs `lcm/o_width` output beats.

```python
sig_10 = Signature(10)
sig_8 = Signature(8)
stride = StrideConverter(sig_10, sig_8)  # 10-bit → 8-bit via LCM=40
```

---

#### `Gearbox`

Non-integer ratio width converter using a shift-register approach. Converts between streams of arbitrary widths (e.g., 10b→8b or 8b→10b).

```python
Gearbox(i_width, o_width, *, has_first_last=False)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `i_width` | `int` | *(required)* | Input data width in bits |
| `o_width` | `int` | *(required)* | Output data width in bits |
| `has_first_last` | `bool` | `False` | Include first/last framing signals |

**Ports:** `i_stream` (In, `Signature(i_width)`), `o_stream` (Out, `Signature(o_width)`)

**Behavior:** Maintains a level counter tracking valid bits in the buffer. Accepts input when there's space, produces output when there's enough data.

```python
gearbox = Gearbox(8, 10)   # 8-bit → 10-bit
gearbox = Gearbox(10, 8)   # 10-bit → 8-bit
```

---

#### `StreamCast`

Zero-cost bit reinterpretation between streams of the same bit width. Wires input payload bits to output payload bits with a different shape interpretation.

```python
StreamCast(i_signature, o_signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input stream signature |
| `o_signature` | `Signature` | Output stream signature (must have same payload bit width) |

**Ports:** `i_stream` (In), `o_stream` (Out)

```python
sig_u16 = Signature(16)
sig_fl = Signature(16, has_first_last=True)
cast = StreamCast(sig_u16, sig_fl)  # Reinterpret 16-bit as 16-bit with framing
```

---

#### `Pack`

Collects N narrow beats into 1 wide beat. Output payload width is `input_width × n`.

```python
Pack(i_signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input (narrow) stream signature |
| `n` | `int` | Number of beats to pack (≥1) |

**Ports:** `i_stream` (In), `o_stream` (Out, width = `i_width × n`)

**Behavior:** Collects `n` input beats into a shift register, then outputs one wide beat. Preserves `first` from beat 0 and `last` from beat `n-1`.

```python
sig_8 = Signature(8, has_first_last=True)
pack4 = Pack(sig_8, 4)  # 4 × 8-bit → 1 × 32-bit
```

---

#### `Unpack`

Splits 1 wide beat into N narrow beats. Input payload width is `output_width × n`.

```python
Unpack(o_signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `o_signature` | `Signature` | Output (narrow) stream signature |
| `n` | `int` | Number of beats to unpack (≥1) |

**Ports:** `i_stream` (In, width = `o_width × n`), `o_stream` (Out)

**Behavior:** Latches one wide input beat, then outputs `n` narrow beats sequentially. `first` appears on beat 0, `last` on beat `n-1`.

```python
sig_8 = Signature(8, has_first_last=True)
unpack4 = Unpack(sig_8, 4)  # 1 × 32-bit → 4 × 8-bit
```

---

### Routing

Defined in [`amaranth_stream/routing.py`](amaranth_stream/routing.py).

#### `StreamMux`

N:1 multiplexer. Selects one of N inputs via `sel`.

```python
StreamMux(signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (identical for all ports) |
| `n` | `int` | Number of input streams (≥1) |

**Ports:** `i_stream__0` .. `i_stream__N-1` (In), `o_stream` (Out), `sel` (In, `range(n)`)

**Methods:** `get_input(i)` — returns the i-th input stream interface.

```python
sig = Signature(8)
mux = StreamMux(sig, 4)
# mux.sel = 2 routes mux.i_stream__2 → mux.o_stream
```

---

#### `StreamDemux`

1:N demultiplexer. Routes input to one of N outputs via `sel`.

```python
StreamDemux(signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (identical for all ports) |
| `n` | `int` | Number of output streams (≥1) |

**Ports:** `i_stream` (In), `o_stream__0` .. `o_stream__N-1` (Out), `sel` (In, `range(n)`)

**Methods:** `get_output(i)` — returns the i-th output stream interface.

**Behavior:** All outputs receive the input payload/sideband signals, but only the selected output gets `valid`. Ready comes from the selected output.

```python
sig = Signature(8)
demux = StreamDemux(sig, 4)
# demux.sel = 1 routes demux.i_stream → demux.o_stream__1
```

---

#### `StreamGate`

Enable/disable gate for a stream.

```python
StreamGate(signature, discard=False)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature |
| `discard` | `bool` | `False` | If `True`, consume and discard when gated; if `False`, apply backpressure |

**Ports:** `i_stream` (In), `o_stream` (Out), `en` (In, 1-bit)

**Behavior:**
- `en=1`: stream passes through normally
- `en=0, discard=False`: backpressure (ready=0, valid=0)
- `en=0, discard=True`: data consumed and discarded (ready=1, valid=0)

```python
sig = Signature(8)
gate = StreamGate(sig, discard=True)
# gate.en controls whether data flows or is discarded
```

---

#### `StreamSplitter`

1:N broadcast/fanout. Synchronized — transfer only occurs when ALL outputs are ready.

```python
StreamSplitter(signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (identical for all ports) |
| `n` | `int` | Number of output streams (≥1) |

**Ports:** `i_stream` (In), `o_stream__0` .. `o_stream__N-1` (Out)

**Methods:** `get_output(i)` — returns the i-th output stream interface.

**Behavior:** All outputs receive the same data simultaneously. Input `ready` is the AND of all output `ready` signals.

```python
sig = Signature(8)
split = StreamSplitter(sig, 3)
# All 3 outputs receive the same data on every transfer
```

---

#### `StreamJoiner`

N:1 interleaved join. Round-robin combining of N inputs.

```python
StreamJoiner(signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (identical for all ports) |
| `n` | `int` | Number of input streams (≥1) |

**Ports:** `i_stream__0` .. `i_stream__N-1` (In), `o_stream` (Out)

**Methods:** `get_input(i)` — returns the i-th input stream interface.

**Behavior:** Selects inputs in round-robin order. Advances to the next input after each successful transfer.

```python
sig = Signature(8)
join = StreamJoiner(sig, 3)
# Interleaves: input 0, input 1, input 2, input 0, ...
```

---

### Packet Processing

Defined in [`amaranth_stream/packet.py`](amaranth_stream/packet.py).

#### `HeaderLayout`

Declarative header definition for packet processing.

```python
HeaderLayout(fields)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `fields` | `dict` | Mapping of `field_name → (width, byte_offset)` |

**Properties:**
- `struct_layout` — `StructLayout` for the header
- `byte_length` — Total header size in bytes
- `fields` — The original fields dict

```python
from amaranth_stream import HeaderLayout

hdr = HeaderLayout({
    "type":   (8, 0),    # 8-bit field at byte offset 0
    "length": (16, 1),   # 16-bit field at byte offset 1
    "flags":  (8, 3),    # 8-bit field at byte offset 3
})
print(hdr.byte_length)  # 4
```

---

#### `Packetizer`

Inserts header beats before payload data. Latches header fields on the first beat.

```python
Packetizer(header_layout, payload_signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `header_layout` | `HeaderLayout` | Header definition |
| `payload_signature` | `Signature` | Stream signature (must have `has_first_last=True`) |

**Ports:** `i_stream` (In), `o_stream` (Out), `header` (In, `header_layout.struct_layout`)

**Behavior:** FSM with HEADER and PAYLOAD states. Emits header beats first (with `first=1` on the first beat), then passes through payload beats until `last=1`.

```python
hdr = HeaderLayout({"type": (8, 0), "length": (16, 1)})
sig = Signature(8, has_first_last=True)
pkt = Packetizer(hdr, sig)
# Set pkt.header.type and pkt.header.length, then send payload on pkt.i_stream
```

---

#### `Depacketizer`

Extracts header from packet start and strips header beats.

```python
Depacketizer(header_layout, payload_signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `header_layout` | `HeaderLayout` | Header definition |
| `payload_signature` | `Signature` | Stream signature (must have `has_first_last=True`) |

**Ports:** `i_stream` (In), `o_stream` (Out), `header` (Out, `header_layout.struct_layout`)

**Behavior:** FSM with HEADER and PAYLOAD states. Consumes header beats, stores them, then passes through payload beats with `first=1` on the first payload beat.

```python
hdr = HeaderLayout({"type": (8, 0), "length": (16, 1)})
sig = Signature(8, has_first_last=True)
depkt = Depacketizer(hdr, sig)
# depkt.header.type and depkt.header.length are available after header is consumed
```

---

#### `PacketFIFO`

Atomic packet FIFO. Only releases complete packets to the output.

```python
PacketFIFO(signature, payload_depth, packet_depth=16)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature (must have `has_first_last=True`) |
| `payload_depth` | `int` | *(required)* | Maximum payload beats |
| `packet_depth` | `int` | `16` | Maximum buffered packets |

**Ports:** `i_stream` (In), `o_stream` (Out), `packet_count` (Out, `range(packet_depth + 1)`)

**Behavior:** Uses a data FIFO for beat storage and a separate packet-length FIFO. Beats are written as they arrive; a packet is "committed" when `last=1`. The read side only starts outputting when a complete packet is available.

```python
sig = Signature(32, has_first_last=True)
pkt_fifo = PacketFIFO(sig, payload_depth=256, packet_depth=8)
# pkt_fifo.packet_count shows how many complete packets are buffered
```

---

#### `PacketStatus`

Packet boundary tracker. Tap-only (does NOT drive `ready`).

```python
PacketStatus(signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (must have `has_first_last=True`) |

**Ports:** `stream` (In, tap-only), `in_packet` (Out, 1-bit)

**Behavior:** Monitors `first` and `last` on transfers. Sets `in_packet` high between `first` and `last`.

```python
sig = Signature(8, has_first_last=True)
status = PacketStatus(sig)
# status.in_packet is high when inside a packet
```

---

#### `Stitcher`

Groups N consecutive packets into one by suppressing intermediate `first`/`last` signals.

```python
Stitcher(signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (must have `has_first_last=True`) |
| `n` | `int` | Number of packets to stitch (≥1) |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:** Only emits `first` on the first beat of the first packet, and `last` on the last beat of the Nth packet. All intermediate `first`/`last` are suppressed.

```python
sig = Signature(8, has_first_last=True)
stitch = Stitcher(sig, 3)
# 3 input packets become 1 output packet
```

---

#### `LastInserter`

Injects `last=1` every N beats, creating fixed-size packets.

```python
LastInserter(signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (must have `has_first_last=True`) |
| `n` | `int` | Packet length in beats (≥1) |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:** Maintains a beat counter. Sets `first=1` on beat 0 and `last=1` on beat `n-1`, then resets.

```python
sig = Signature(8, has_first_last=True)
inserter = LastInserter(sig, 64)
# Creates 64-beat packets from a continuous stream
```

---

#### `LastOnTimeout`

Injects `last=1` after a configurable idle timeout.

```python
LastOnTimeout(signature, timeout)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (must have `has_first_last=True`) |
| `timeout` | `int` | Idle cycles before injecting `last` (≥1) |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:** Tracks idle cycles (no transfer) while inside a packet. When the idle counter reaches `timeout`, forces `last=1` on the next transfer.

```python
sig = Signature(8, has_first_last=True)
timeout = LastOnTimeout(sig, timeout=100)
# If no data for 100 cycles mid-packet, forces packet termination
```

---

### Arbitration

Defined in [`amaranth_stream/arbiter.py`](amaranth_stream/arbiter.py).

#### `StreamArbiter`

Packet-aware N:1 arbiter. Holds grant until `last` to ensure packet integrity.

```python
StreamArbiter(signature, n, *, round_robin=True)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature (must have `has_first_last=True`) |
| `n` | `int` | *(required)* | Number of input streams (≥1) |
| `round_robin` | `bool` | `True` | Round-robin arbitration; if `False`, priority (lower index = higher) |

**Ports:** `i_stream__0` .. `i_stream__N-1` (In), `o_stream` (Out), `grant` (Out, `range(n)`)

**Methods:** `get_input(i)` — returns the i-th input stream interface.

**Behavior:** When unlocked, selects the next valid input (round-robin or priority). On `first` (without `last`), locks the grant until `last` is seen, ensuring complete packets are forwarded.

```python
sig = Signature(32, has_first_last=True)
arb = StreamArbiter(sig, 4, round_robin=True)
# arb.grant shows which input currently has the grant
```

---

#### `StreamDispatcher`

Packet-aware 1:N dispatcher. Latches `sel` on `first`, holds until `last`.

```python
StreamDispatcher(signature, n)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (must have `has_first_last=True`) |
| `n` | `int` | Number of output streams (≥1) |

**Ports:** `i_stream` (In), `o_stream__0` .. `o_stream__N-1` (Out), `sel` (In, `range(n)`)

**Methods:** `get_output(i)` — returns the i-th output stream interface.

**Behavior:** On the first beat of a packet (`first` without `last`), latches the current `sel` value. Holds the latched selection until `last`, ensuring the entire packet goes to the same output.

```python
sig = Signature(32, has_first_last=True)
disp = StreamDispatcher(sig, 4)
# Set disp.sel before each packet; it's latched on first beat
```

---

### Data Transformation

Defined in [`amaranth_stream/transform.py`](amaranth_stream/transform.py).

#### `StreamMap`

Combinational payload transformation via a user-provided function.

```python
StreamMap(i_signature, o_signature, transform)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `i_signature` | `Signature` | Input stream signature |
| `o_signature` | `Signature` | Output stream signature |
| `transform` | `callable` | `transform(m, payload_in)` → payload expression |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:** Calls `transform(m, payload_in)` during elaboration to create combinational logic. Passes through `valid`/`ready`/`first`/`last`/`param`/`keep` unchanged.

```python
sig_8 = Signature(8)
sig_16 = Signature(16)

# Double the payload value
mapper = StreamMap(sig_8, sig_16, lambda m, p: p << 1)
```

---

#### `StreamFilter`

Conditional beat dropping via a user-provided predicate.

```python
StreamFilter(signature, predicate)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature |
| `predicate` | `callable` | `predicate(m, payload)` → `Signal(1)`. Returns 1 to pass, 0 to drop. |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:** When the predicate returns 0, the beat is consumed (input `ready=1`) but not forwarded to the output (`valid=0`). When the predicate returns 1, the beat passes through normally.

```python
sig = Signature(8)

# Pass only even values
filt = StreamFilter(sig, lambda m, p: ~p[0])
```

---

#### `EndianSwap`

Byte-order reversal. Payload must be a multiple of 8 bits.

```python
EndianSwap(signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature (payload width must be multiple of 8) |

**Ports:** `i_stream` (In), `o_stream` (Out)

**Behavior:** Reverses the byte order of the payload. For a 32-bit payload `0xAABBCCDD`, the output is `0xDDCCBBAA`.

```python
sig = Signature(32, has_first_last=True)
swap = EndianSwap(sig)
```

---

#### `ByteAligner`

Sub-word byte alignment with configurable shift.

```python
ByteAligner(signature, max_shift)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature |
| `max_shift` | `int` | Maximum shift in bytes (≥1) |

**Ports:** `i_stream` (In), `o_stream` (Out), `shift` (In, `range(max_shift + 1)`)

**Behavior:** Barrel-shifts the payload left by `shift × 8` bits.

```python
sig = Signature(32)
aligner = ByteAligner(sig, max_shift=3)
# aligner.shift = 1 shifts payload left by 8 bits
```

---

### Monitoring & Debug

Defined in [`amaranth_stream/monitor.py`](amaranth_stream/monitor.py).

#### `StreamMonitor`

Performance counters with tap-through. Passes all signals unchanged while counting events.

```python
StreamMonitor(signature, counter_width=32)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signature` | `Signature` | *(required)* | Stream signature |
| `counter_width` | `int` | `32` | Width of performance counters |

**Ports:**
- `i_stream` (In) — tap-through input
- `o_stream` (Out) — identical to input
- `transfer_count` (Out) — completed transfers (`valid & ready`)
- `stall_count` (Out) — stall cycles (`valid & ~ready`)
- `idle_count` (Out) — idle cycles (`~valid & ready`)
- `packet_count` (Out) — completed packets (`valid & ready & last`)
- `clear` (In) — reset all counters to 0

```python
sig = Signature(32, has_first_last=True)
mon = StreamMonitor(sig)
# Insert in-line: source → mon.i_stream, mon.o_stream → sink
# Read mon.transfer_count, mon.stall_count, etc.
```

---

#### `StreamChecker`

Protocol assertion checker for simulation. Monitors a stream for protocol violations.

```python
StreamChecker(signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `signature` | `Signature` | Stream signature |

**Ports:** `stream` (In, tap-only — does NOT drive `ready`), `error` (Out, 1-bit, sticky)

**Checks:**
- Once `valid` is asserted, `payload` must not change until transfer
- Once `valid` is asserted, `valid` must not deassert until transfer
- If `has_first_last`, `first`/`last` must not change while `valid & ~ready`

```python
sig = Signature(8, has_first_last=True)
checker = StreamChecker(sig)
# checker.error goes high (and stays high) on any protocol violation
```

---

### AXI-Stream Bridge

Defined in [`amaranth_stream/axi_stream.py`](amaranth_stream/axi_stream.py).

#### `AXIStreamSignature`

AXI-Stream interface definition. Subclass of `wiring.Signature`.

```python
AXIStreamSignature(data_width, *, id_width=0, dest_width=0, user_width=0)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_width` | `int` | *(required)* | TDATA width in bits (must be multiple of 8) |
| `id_width` | `int` | `0` | TID width (0 to omit) |
| `dest_width` | `int` | `0` | TDEST width (0 to omit) |
| `user_width` | `int` | `0` | TUSER width (0 to omit) |

**Members:** `tdata`, `tvalid`, `tready`, `tkeep`, `tstrb`, `tlast`, and optionally `tid`, `tdest`, `tuser`.

```python
from amaranth_stream import AXIStreamSignature

axi_sig = AXIStreamSignature(32, id_width=4, user_width=8)
```

---

#### `AXIStreamToStream`

AXI-Stream → amaranth_stream bridge.

```python
AXIStreamToStream(axi_signature, stream_signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `axi_signature` | `AXIStreamSignature` | AXI-Stream interface signature |
| `stream_signature` | `Signature` | Output stream signature (should have `has_first_last=True`, `has_keep=True`) |

**Ports:** `axi` (In, AXI-Stream), `o_stream` (Out, amaranth_stream)

**Behavior:** Maps `tdata→payload`, `tvalid→valid`, `tready←ready`, `tlast→last`, `tkeep→keep`. Tracks `first` internally (first beat after reset or after `tlast`).

```python
axi_sig = AXIStreamSignature(32)
stream_sig = Signature(32, has_first_last=True, has_keep=True)
bridge = AXIStreamToStream(axi_sig, stream_sig)
```

---

#### `StreamToAXIStream`

amaranth_stream → AXI-Stream bridge.

```python
StreamToAXIStream(stream_signature, axi_signature)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `stream_signature` | `Signature` | Input stream signature |
| `axi_signature` | `AXIStreamSignature` | AXI-Stream output signature |

**Ports:** `i_stream` (In, amaranth_stream), `axi` (Out, AXI-Stream)

**Behavior:** Maps `payload→tdata`, `valid→tvalid`, `ready←tready`, `last→tlast`, `keep→tkeep`. Sets `tstrb=tkeep`. If the stream has no `keep`, defaults `tkeep` and `tstrb` to all-ones.

```python
stream_sig = Signature(32, has_first_last=True, has_keep=True)
axi_sig = AXIStreamSignature(32)
bridge = StreamToAXIStream(stream_sig, axi_sig)
```

---

## Testing

The test suite contains **260 passing tests** covering all components.

```bash
# Run all tests
pdm run python -m pytest tests/ -v

# Run tests for a specific module
pdm run python -m pytest tests/test_buffer.py -v
pdm run python -m pytest tests/test_fifo.py -v
pdm run python -m pytest tests/test_converter.py -v

# Run with VCD waveform output (tests generate .vcd files)
pdm run python -m pytest tests/ -v --tb=short
```

### Test Organization

| Test File | Coverage |
|-----------|----------|
| `tests/test_base.py` | Signature, Interface, core_to_extended |
| `tests/test_sim.py` | StreamSimSender, StreamSimReceiver |
| `tests/test_buffer.py` | Buffer, PipeValid, PipeReady, Delay |
| `tests/test_fifo.py` | StreamFIFO, StreamAsyncFIFO |
| `tests/test_cdc.py` | StreamCDC |
| `tests/test_converter.py` | StreamConverter, StrideConverter, Gearbox, StreamCast, Pack, Unpack |
| `tests/test_routing.py` | StreamMux, StreamDemux, StreamGate, StreamSplitter, StreamJoiner |
| `tests/test_packet.py` | Packetizer, Depacketizer, PacketFIFO, PacketStatus, Stitcher, LastInserter, LastOnTimeout |
| `tests/test_arbiter.py` | StreamArbiter, StreamDispatcher |
| `tests/test_pipeline.py` | Pipeline, BufferizeEndpoints |
| `tests/test_transform.py` | StreamMap, StreamFilter, EndianSwap, ByteAligner |
| `tests/test_monitor.py` | StreamMonitor, StreamChecker |
| `tests/test_axi_stream.py` | AXIStreamSignature, AXIStreamToStream, StreamToAXIStream |
| `tests/test_integration.py` | Multi-component integration tests |

---

## Architecture

### Design Philosophy

1. **Composable Components** — Every component is a `wiring.Component` with standardized `i_stream`/`o_stream` ports, making them trivially chainable via `Pipeline` or manual `connect()` calls.

2. **Extended Signature** — The `Signature` class extends Amaranth's built-in `stream.Signature` (which is `@final`) with optional `first`/`last` packet framing, `param` sideband data, and `keep` byte enables — all without subclassing the sealed core class.

3. **Signal Preservation** — All components correctly propagate optional signals (`first`, `last`, `param`, `keep`) through the pipeline when both input and output signatures include them.

4. **Simulation-First** — The `StreamSimSender` and `StreamSimReceiver` BFMs use `ctx.tick().sample()` for race-free signal capture, and support `random_valid`/`random_ready` modes for stress testing.

5. **Packet Awareness** — Arbitration (`StreamArbiter`, `StreamDispatcher`) and routing components respect packet boundaries, locking grants/selections from `first` to `last` to prevent packet interleaving.

6. **Zero-Copy Where Possible** — Components like `StreamCast` and identity-mode converters are pure combinational wire-throughs with no registers or latency.

### Component Count

| Category | Components |
|----------|-----------|
| Core | 3 (Signature, Interface, core_to_extended) |
| Simulation BFMs | 2 |
| Buffering & Pipeline | 6 |
| FIFOs & CDC | 3 |
| Width Conversion | 6 |
| Routing | 5 |
| Packet Processing | 8 |
| Arbitration | 2 |
| Data Transformation | 4 |
| Monitoring & Debug | 2 |
| AXI-Stream Bridge | 3 |
| **Total** | **44** |

---

## License

See the project repository for license information.
