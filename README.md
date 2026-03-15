# amaranth-stream

A comprehensive stream processing library for [Amaranth HDL](https://amaranth-lang.org/) providing 44 public components for building high-performance streaming data pipelines in digital hardware.

**amaranth-stream** extends Amaranth's built-in stream primitives with optional packet framing (`first`/`last`), sideband parameters (`param`), byte-enable masks (`keep`), and a rich set of components for buffering, width conversion, routing, packet processing, arbitration, data transformation, monitoring, and AXI-Stream bridging.

See the full [API Reference](https://github.com/key2/amaranth-stream) in the repository.

## Installation

```bash
git clone https://github.com/key2/amaranth-stream.git
cd amaranth-stream
pdm install
```

## Quick Start

```python
from amaranth_stream import Signature, Buffer, StreamSimSender, StreamSimReceiver

# 8-bit stream with packet framing
sig = Signature(8, has_first_last=True)
buf = Buffer(sig)
```

## Components (44 total)

- **Core**: Signature, Interface, core_to_extended
- **Sim BFMs**: StreamSimSender, StreamSimReceiver
- **Buffering**: Buffer, PipeValid, PipeReady, Delay
- **FIFOs & CDC**: StreamFIFO, StreamAsyncFIFO, StreamCDC
- **Width Conversion**: StreamConverter, StrideConverter, Gearbox, StreamCast, Pack, Unpack
- **Routing**: StreamMux, StreamDemux, StreamGate, StreamSplitter, StreamJoiner
- **Packet Processing**: HeaderLayout, Packetizer, Depacketizer, PacketFIFO, PacketStatus, Stitcher, LastInserter, LastOnTimeout
- **Arbitration**: StreamArbiter, StreamDispatcher
- **Pipeline**: Pipeline, BufferizeEndpoints
- **Transform**: StreamMap, StreamFilter, EndianSwap, ByteAligner
- **Monitor**: StreamMonitor, StreamChecker
- **AXI Bridge**: AXIStreamSignature, AXIStreamToStream, StreamToAXIStream

## Testing

260 tests passing across 13 test files.

```bash
pdm run python -m pytest tests/ -v
```

## License

See the project repository for license information.
