"""amaranth-stream: Extended stream processing library for Amaranth HDL."""

from ._base import Signature, Interface, core_to_extended, connect_streams
from .sim import StreamSimSender, StreamSimReceiver
from .buffer import Buffer, PipeValid, PipeReady, Delay
from .fifo import StreamFIFO, StreamAsyncFIFO
from .cdc import StreamCDC
from .converter import (
    StreamConverter,
    StrideConverter,
    Gearbox,
    StreamCast,
    Pack,
    Unpack,
    ByteEnableSerializer,
)
from .routing import (
    StreamMux,
    StreamDemux,
    StreamGate,
    StreamSplitter,
    StreamJoiner,
)
from .packet import (
    HeaderLayout,
    Packetizer,
    Depacketizer,
    PacketFIFO,
    PacketStatus,
    Stitcher,
    LastInserter,
    LastOnTimeout,
)
from .arbiter import StreamArbiter, StreamDispatcher
from .pipeline import Pipeline, BufferizeEndpoints
from .transform import StreamMap, StreamFilter, EndianSwap, GranularEndianSwap, ByteAligner, PacketAligner, WordReorder
from .monitor import StreamMonitor, StreamChecker, StreamProtocolChecker
from .axi_stream import AXIStreamSignature, AXIStreamToStream, StreamToAXIStream
from .adapter import SOPEOPAdapter, StreamToSOPEOP

__all__ = [
    "Signature",
    "Interface",
    "core_to_extended",
    "StreamSimSender",
    "StreamSimReceiver",
    "Buffer",
    "PipeValid",
    "PipeReady",
    "Delay",
    "StreamFIFO",
    "StreamAsyncFIFO",
    "StreamCDC",
    "StreamConverter",
    "StrideConverter",
    "Gearbox",
    "StreamCast",
    "Pack",
    "Unpack",
    "StreamMux",
    "StreamDemux",
    "StreamGate",
    "StreamSplitter",
    "StreamJoiner",
    "HeaderLayout",
    "Packetizer",
    "Depacketizer",
    "PacketFIFO",
    "PacketStatus",
    "Stitcher",
    "LastInserter",
    "LastOnTimeout",
    "StreamArbiter",
    "StreamDispatcher",
    "Pipeline",
    "BufferizeEndpoints",
    "StreamMap",
    "StreamFilter",
    "EndianSwap",
    "GranularEndianSwap",
    "ByteAligner",
    "PacketAligner",
    "WordReorder",
    "StreamMonitor",
    "StreamChecker",
    "StreamProtocolChecker",
    "AXIStreamSignature",
    "AXIStreamToStream",
    "StreamToAXIStream",
    "SOPEOPAdapter",
    "StreamToSOPEOP",
    "ByteEnableSerializer",
    "connect_streams",
]
