# amaranth-stream Improvement Roadmap

*Based on analysis of amaranth-pcie, amaranth-soc, and real-world PCIe/DMA usage on Gowin GW5AST and Xilinx Series 7 FPGAs.*

---

## Priority Legend

- 🔴 **P0 — Critical Bug**: Causes incorrect behavior or deadlock
- 🟠 **P1 — Major Gap**: Forces users to write complex custom implementations
- 🟡 **P2 — Important Enhancement**: Improves usability and reduces boilerplate
- 🟢 **P3 — Nice to Have**: Quality-of-life improvements

---

## 🔴 P0 — Critical Bugs

### 1. StrideConverter Short-Packet Deadlock

**File:** [`converter.py:342-392`](amaranth_stream/converter.py:342)

**Bug:** When converting from narrow to wide (e.g., 64→256), the FILL state waits for `i_ratio` input beats before transitioning to DRAIN. If a packet's `last` beat arrives before the LCM buffer is full (e.g., a 2-beat packet on a 4:1 converter), the FSM stalls forever — the remaining beats never arrive because the packet has ended.

**Impact:** Any variable-length packet protocol (PCIe TLPs, Ethernet frames, USB packets) will deadlock on short packets when using StrideConverter for upconversion.

**Fix:** When `last` is captured during FILL, transition to DRAIN immediately on the next cycle, padding the unfilled portion with zeros and setting appropriate byte enables. The `last` flag should propagate to the final DRAIN beat.

**Test needed:** `test_stride_converter_short_packet_upsize` — send a 2-beat packet through a 4:1 converter, verify it produces 1 output beat with `last=1` and correct padding.

**Workaround in amaranth-pcie:** PCIe TLPs are always DWORD-aligned and padded via byte enables, so short packets that don't fill the buffer don't occur in practice. But this is a latent bug for general use.

---

### 2. Packetizer/Depacketizer Cannot Handle Sub-Beat Header Boundaries

**File:** [`packet.py:122-336`](amaranth_stream/packet.py:122)

**Bug:** The `Packetizer` emits `header_beats` complete beats of header data, then switches to payload passthrough. It cannot merge the last header DWORD with the first payload DWORD in the same beat. Similarly, the `Depacketizer` assumes headers occupy whole beats.

**Impact:** PCIe 3DW headers are 96 bits. On a 64-bit bus, beat 1 = DW0+DW1, beat 2 = DW2 + first payload DWORD. The current Packetizer would emit 2 full header beats (128 bits, wasting 32 bits), then start payload — it cannot merge DW2 with payload. This forced amaranth-pcie to implement **6 custom header inserter/extracter classes**:
- [`TLPHeaderInserter64b3DWs`](../amaranth-pcie/amaranth_pcie/tlp/packetizer.py:57)
- [`TLPHeaderInserter64b4DWs`](../amaranth-pcie/amaranth_pcie/tlp/packetizer.py:155)
- [`TLPHeaderInserterNDWs`](../amaranth-pcie/amaranth_pcie/tlp/packetizer.py:353)
- [`TLPHeaderExtracter64b`](../amaranth-pcie/amaranth_pcie/tlp/depacketizer.py:68)
- [`TLPHeaderExtracter`](../amaranth-pcie/amaranth_pcie/tlp/depacketizer.py:238)
- [`TLPHeaderInserter64b`](../amaranth-pcie/amaranth_pcie/tlp/packetizer.py:238)

**Fix:** Add a `packed=True` mode to `Packetizer`/`Depacketizer` that handles sub-beat header alignment. When the header doesn't end on a beat boundary, the remaining space in the last header beat is filled with the first payload bytes. On the depacketizer side, the header extraction should shift the payload to account for the partial header beat.

**Test needed:** `test_packetizer_packed_96bit_header_64bit_bus` — 96-bit header on 64-bit bus, verify DW2 shares beat with first payload DWORD.

---

## 🟠 P1 — Major Gaps

### 3. No SOP/EOP Protocol Adapter

**Gap:** No component converts between SOP/EOP/valid-mask framing (common in FPGA hard IP blocks) and amaranth-stream's valid/ready/first/last framing.

**Impact:** Forced creation of [`GowinTLPAdapter`](../amaranth-pcie/amaranth_pcie/phy/gowin.py:41) (130 lines) for the Gowin PCIe IP. Similar adapters would be needed for Xilinx Aurora, Intel Avalon-ST, and other vendor IP.

**Proposed component:** `SOPEOPAdapter`

```python
class SOPEOPAdapter(Elaboratable):
    """Converts SOP/EOP/valid-mask interface to valid/ready/first/last stream.
    
    Parameters:
        data_width: Width of data bus (e.g., 256)
        valid_granularity: Granularity of valid mask (e.g., 32 for DWORD-level)
        has_backpressure: Whether the source supports backpressure (wait signal)
    """
```

**Features needed:**
- SOP → `first`, EOP → `last` mapping
- `valid[N:0]` mask → `be[M:0]` byte enable expansion
- Optional DWORD/word reordering (configurable order map)
- Backpressure mapping (`wait ↔ ~ready`)
- Configurable valid-mask granularity (bit, byte, DWORD)

**Test needed:** `test_sop_eop_adapter_256bit_dword_valid` — 256-bit data with 8-bit DWORD valid mask.

---

### 4. No Cross-Beat Data Realignment

**Gap:** No stream primitive handles the case where packets start at non-zero offsets within a wide data word and data must be stitched across beat boundaries.

**Impact:** Forced creation of [`PHYRX128BAligner`](../amaranth-pcie/amaranth_pcie/phy/common.py:144) (77 lines) — a 2-state FSM that stores the upper half of the previous beat and combines it with the lower half of the current beat.

**Existing component:** [`ByteAligner`](amaranth_stream/transform.py:205) does combinational barrel shifting within a single beat but cannot stitch across beats.

**Proposed component:** `PacketAligner`

```python
class PacketAligner(Elaboratable):
    """Realigns packet data when packets start at non-zero offsets.
    
    Handles the case where a packet's first valid data starts at an offset
    within the data word (e.g., DWORD2 of a 128-bit word). Uses a shift
    register to stitch data across beat boundaries.
    
    Parameters:
        signature: Stream signature
        alignment: Alignment granularity in bits (e.g., 32 for DWORD)
        offset_signal: Signal indicating the start offset of each packet
    """
```

**Test needed:** `test_packet_aligner_128bit_dword2_start` — packets starting at DWORD2 of 128-bit words.

---

### 5. No Per-DWORD Endian Swap

**Gap:** [`EndianSwap`](amaranth_stream/transform.py:147) reverses all bytes across the full data width. PCIe (and many other protocols) need per-DWORD (32-bit) byte reversal — each 32-bit chunk is byte-swapped independently.

**Impact:** Forced creation of [`dword_endianness_swap()`](../amaranth-pcie/amaranth_pcie/tlp/common.py:379) as a standalone function, and inline [`_byte_swap_32()`](../amaranth-pcie/amaranth_pcie/frontend/wishbone.py:110) in the Wishbone frontend.

**Proposed component:** `GranularEndianSwap`

```python
class GranularEndianSwap(Elaboratable):
    """Byte-reversal within fixed-size chunks of the data word.
    
    Parameters:
        signature: Stream signature
        granularity: Chunk size in bits (default 32 for DWORD)
        field: Which payload field to swap (default "dat")
        mode: "dat" for data bytes, "be" for byte-enable nibbles
    """
```

**Also add:** A `be` mode that reverses byte-enable bits within each granularity-sized group (needed for PCIe byte enable handling).

**Test needed:** `test_granular_endian_swap_256bit_dword` — 256-bit data, verify each 32-bit DWORD is independently byte-reversed.

---

### 6. StrideConverter Doesn't Propagate Sideband/Param Fields

**Gap:** The `StrideConverter` only propagates `first`/`last` through width conversion. Sideband fields that are valid on the first beat (like PCIe's `bar_hit`) are lost on subsequent output beats.

**Impact:** Forced creation of `bar_hit` latching logic in [`gowin.py:650-655`](../amaranth-pcie/amaranth_pcie/phy/gowin.py:650).

**Fix:** Add `param_shape` support to `StrideConverter`. Param fields should be captured on the first input beat (when `first=1`) and held constant for all output beats of the same packet.

**Test needed:** `test_stride_converter_param_propagation` — verify sideband field is held across all output beats.

---

### 7. No Byte-Enable-Aware Serializer

**Gap:** No component converts a wide stream with byte enables into a narrow stream emitting only valid bytes.

**Impact:** Forced creation of [`TLPGearbox`](../sniffer/pcie_sniffer/gearbox.py:34) in the sniffer project — a custom 256-bit→8-bit serializer that skips bytes where BE=0.

**Proposed component:** `ByteEnableSerializer`

```python
class ByteEnableSerializer(Elaboratable):
    """Serializes a wide stream with byte enables into a narrow byte stream.
    
    Only emits bytes where the corresponding byte enable is set.
    Preserves packet boundaries (first/last).
    
    Parameters:
        i_signature: Input stream signature (must have 'dat' and 'be' fields)
        o_width: Output data width in bits (default 8)
    """
```

**Test needed:** `test_be_serializer_256to8_sparse` — 256-bit input with sparse BE, verify only valid bytes emitted.

---

## 🟡 P2 — Important Enhancements

### 8. StreamCDC Same-Domain Optimization

**File:** [`cdc.py:62-66`](amaranth_stream/cdc.py:62)

**Issue:** When `w_domain == r_domain`, `StreamCDC` instantiates a full `Buffer` (both `pipe_valid` and `pipe_ready`), adding 2 cycles of latency. A `PipeValid` alone would suffice for same-domain use.

**Fix:** Use `PipeValid` instead of `Buffer` for same-domain case.

---

### 9. PacketFIFO Drop-on-Error

**File:** [`packet.py:343-475`](amaranth_stream/packet.py:343)

**Gap:** `PacketFIFO` provides atomic packet buffering but has no mechanism to drop a packet if an error is detected mid-packet.

**Impact:** PCIe requires dropping malformed TLPs. Without drop support, the FIFO must be drained even for bad packets.

**Fix:** Add an `abort` input signal. When asserted during a packet (between `first` and `last`), the FIFO discards all data written since the last `first` and resets the write pointer.

**Test needed:** `test_packet_fifo_abort_mid_packet` — write partial packet, assert abort, verify FIFO is empty.

---

### 10. Word Reorder Transform

**Gap:** No generic component for reordering words within a data beat (e.g., reversing 8 DWORDs in a 256-bit word).

**Impact:** Forced inline DWORD reversal in [`GowinTLPAdapter`](../amaranth-pcie/amaranth_pcie/phy/gowin.py:113).

**Proposed component:** `WordReorder`

```python
class WordReorder(Elaboratable):
    """Reorders fixed-size words within a data beat.
    
    Parameters:
        signature: Stream signature
        word_width: Width of each word in bits (e.g., 32)
        order: Tuple of indices specifying output order (e.g., (7,6,5,4,3,2,1,0) for reversal)
        field: Which payload field to reorder (default "dat")
    """
```

---

### 11. Stream Connect Helper

**Gap:** Connecting two stream interfaces requires manual wiring of `payload`, `valid`, `ready`, `first`, `last`. The `wiring.connect()` function doesn't always handle extended stream signatures seamlessly.

**Impact:** Forced creation of `_connect_streams()` helpers in [`crossbar.py:54`](../amaranth-pcie/amaranth_pcie/core/crossbar.py:54) and [`dma.py:59`](../amaranth-pcie/amaranth_pcie/frontend/dma.py:59).

**Fix:** Provide a `connect_streams(m, src, dst)` utility function in amaranth-stream that handles all stream fields correctly, including `first`, `last`, `param`, and `keep`.

---

### 12. HeaderLayout Bit-Level Field Support

**File:** [`packet.py:74-116`](amaranth_stream/packet.py:74)

**Gap:** `HeaderLayout` stores fields as `(width, byte_offset)` pairs. PCIe TLP headers pack multiple fields within the same DWORD at specific bit offsets (e.g., `fmt(2)`, `type(5)`, `tc(3)` all at byte_offset=0).

**Fix:** Add optional `bit_offset` parameter to `HeaderLayout` fields, allowing bit-level field placement within a byte-aligned region.

---

## 🟢 P3 — Nice to Have

### 13. AXI-Stream `first` Signal Support

**File:** [`axi_stream.py:18-102`](amaranth_stream/axi_stream.py:18)

**Gap:** `AXIStreamSignature` has `tlast` but no `tfirst`. The [`AXIStreamToStream`](amaranth_stream/axi_stream.py:105) bridge synthesizes `first` from state tracking, adding latency.

**Fix:** Add optional `tfirst` support to `AXIStreamSignature` (non-standard but useful for bridging).

---

### 14. Stream Monitor Protocol Checker

**File:** [`monitor.py`](amaranth_stream/monitor.py:1)

**Enhancement:** Add protocol checking assertions:
- `first` must follow `last` (no `first` without preceding `last` or start-of-stream)
- `valid` must not deassert mid-packet (between `first` and `last`) without `ready` being low
- `payload` must be stable when `valid=1` and `ready=0`

---

### 15. Gearbox Non-Integer Ratio with Packet Awareness

**File:** [`converter.py:395`](amaranth_stream/converter.py:395)

**Gap:** The `Gearbox` handles non-integer ratios via shift register but is not packet-aware (no `first`/`last` handling).

**Fix:** Add `first`/`last` propagation to `Gearbox`, with proper handling of partial last beats.

---

## Implementation Order

```
Phase 1 (Critical — unblocks PCIe and similar protocols):
  [1] StrideConverter short-packet fix
  [2] Packetizer/Depacketizer packed mode
  [3] SOP/EOP Protocol Adapter
  [5] GranularEndianSwap

Phase 2 (Major gaps — reduces custom code):
  [4] PacketAligner
  [6] StrideConverter param propagation
  [7] ByteEnableSerializer
  [11] Stream connect helper

Phase 3 (Enhancements):
  [8] StreamCDC same-domain optimization
  [9] PacketFIFO drop-on-error
  [10] WordReorder
  [12] HeaderLayout bit-level fields

Phase 4 (Polish):
  [13] AXI-Stream first support
  [14] Stream Monitor protocol checker
  [15] Gearbox packet awareness
```

---

*This roadmap is derived from the analysis in [`ANALYSIS.md`](../amaranth-pcie/ANALYSIS.md) and [`WISHBONE_VS_AXI4.md`](../amaranth-pcie/WISHBONE_VS_AXI4.md).*
