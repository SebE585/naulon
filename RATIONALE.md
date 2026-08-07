# Rationale

Where the numbers in `model/constants.yaml` come from, and what is still owed.

This file exists because a calculator with invented constants is a machine for
producing confident wrong answers. Anything asserted here should be checkable
by someone who does not trust us.

---

## Record framing

**What it means.** The per-record envelope: everything on the wire that is not
a semantic field. Sync words, length prefixes, message type tags, checksums,
terminators.

**Convention for the boundary.** A sequence counter is a modelled field
(`sequence_counter`), not framing — it carries information a consumer can use.
A message type tag is framing.

### The single-constant model was wrong

Version 0.1.0 of this file carried one value, 50 bytes, with a note claiming an
observed range of 40–60 bytes across binary telematics protocols. That note was
not sourced, and sourcing it showed it to be wrong: **binary protocols frame a
record in 8 to 10 bytes, not 50.** The placeholder was roughly five times too
high, and it propagated into every published figure in the repository.

Nothing had been published as measured, because the CLI and the library flagged
`framing.record_framing_bytes` as `to_source` in every report. That is what the
status field is for.

The correction also showed why one number could never have worked: framing is a
**regime**, and the regimes are an order of magnitude apart.

### binary_framed — 8 bytes, sourced

Two independently specified binary protocols converge.

**UBX (u-blox).** Every frame carries 2 sync bytes (`0xB5 0x62`), 1 message
class byte, 1 message ID byte, a 2-byte payload length field, and a 2-byte
checksum. The length field explicitly counts the payload only. Total: **8 bytes**.

- [UBX Protocol frame structure, SparkFun GNSS documentation](https://docs.sparkfun.com/SparkFun_GNSS_Flex_System/SparkPNT_GNSS_Flex_Module_DAN-F10N/ubx_protocol/) — consulted 2026-08-07
- *Reservation:* secondary source. The primary u-blox Interface Description
  (UBX-13003221) states the same structure but has not been read directly.
  Promote this entry when it has.

**GT06 (Concox).** 2 start bytes (`0x78 0x78`), 1 length byte, 1 protocol number
byte, a 2-byte information serial number, a 2-byte CRC-ITU, and 2 stop bytes
(`0x0D 0x0A`). That is 10 bytes of non-payload material, of which the 2-byte
serial is reassigned to `sequence_counter` under our convention, leaving
**8 bytes** of framing.

- [GT06 protocol packet format](https://traxelio.com/trackers/protocol/gt06) — consulted 2026-08-07
- *Reservation:* the page states 12 bytes of overhead while its own byte table
  sums to 10. The value used here is recomputed from the table.
- Cross-check: the same page gives roughly 30 bytes for a complete position
  record, of which about 18 bytes is GPS body — consistent with 8 bytes of
  framing plus a serial.

### bit_packed — 4 bytes, sourced

Bit-packed radio protocols carry almost no in-message framing, because the
framing lives in the physical layer rather than the message.

**AIS message type 1** (Position Report Class A) is 168 bits in total. Its
non-navigation content is message type (6 bits), repeat indicator (2), spare
(3), RAIM flag (1) and radio status (19) — **31 bits, so 4 bytes**. Everything
else is navigation payload, including the 30-bit MMSI, which the model treats
as `device_id`.

- [AIVDM/AIVDO protocol decoding, message type 1](https://gpsd.gitlab.io/gpsd/AIVDM.html) — consulted 2026-08-07

### ascii_delimited — 60 bytes, still a placeholder

Text protocols pay several times binary for identical semantics: field
separators, decimal rather than binary representation, and a long fixed
preamble repeated on every record.

A Queclink @Track position record runs to roughly 180 characters, a large share
of which is prefix, message type, device identity, model name, device name,
counters, checksum and terminator.

- [Queclink @Track Air Interface Protocol](https://www.traccar.org/protocol/5004-gl200/GT300%20@Track%20Air%20Interface%20Protocol%20V4.02.pdf) — located 2026-08-07
- **Status: `to_source`.** The 60-byte value is an estimate. It has *not* been
  derived field by field from the specification. Do not publish a figure that
  depends on this regime until it has been.

---

## Batch framing

**16 bytes, derived** from SenML (RFC 8428) encoded in CBOR (RFC 8949).

A SenML Pack is an array of Records whose base fields — base name, base time,
base value, base unit, base sum, base version — are carried **once for the whole
pack**, after which each record carries only its offset from them. The
specification is explicit: base time and time are added together to get the time
of measurement; base value and value are added together to get the value.

That is batching plus delta encoding, specified in a Standards Track RFC. The
`event_driven` profile is not an architecture we invented; it is a documented
one.

Byte count for one pack wrapper: CBOR definite-length array header 1 byte
(2 beyond 23 records), plus the base fields in the first record's map — map
header 1, `bver` label and value 2 (often omitted, default 10), `bn` label plus
text header plus a short base name about 10, `bt` label plus a 32-bit epoch 6.
Between 10 and 20 bytes; 16 is the midpoint.

- [RFC 8428, Sensor Measurement Lists (SenML)](https://www.rfc-editor.org/rfc/rfc8428.html) — consulted 2026-08-07

*Caveat:* this is a derivation from two specifications, not a measurement of a
telematics product. A protocol using a fixed binary preamble and a CRC would
land lower.

### A compactness data point, and what it does not say

RFC 8428's own worked example encodes to 254 bytes in CBOR against 573 bytes in
JSON — 44 %, a factor of about 2.3.

That measures **binary against text**, not the gain from delta encoding. It is
evidence for the framing regimes in this file. It is *not* a source for
`compression_ratio`, and it must not be cited as one.

### Unmodelled second-order effect: delta encoding rewards density

Google's Encoded Polyline Algorithm — delta, then zigzag, then 5-bit varint
chunks, at 1e-5 degree scaling — notes that compression is most effective when
consecutive coordinates are close together.

The consequence runs in an interesting direction for this model. Under delta
encoding, **raising the acquisition rate shrinks the deltas, so each additional
position costs fewer bytes than the last**. Derived from the published
algorithm at 90 km/h: roughly 3 000 m between fixes at 120 s needs three chunks
per coordinate, while 250 m at 10 s needs two.

**Naulon does not model this.** The marginal cost of a position is treated as a
constant, which is the conservative choice: a real delta-encoded deployment will
do slightly better than Naulon predicts when densifying, never worse. Modelling
it would require a vehicle-speed parameter and would turn a flat statement —
*the marginal cost is constant* — into a conditional one, at the cost of the
argument's simplicity.

- [Encoded Polyline Algorithm Format](https://developers.google.com/maps/documentation/utilities/polylinealgorithm) — consulted 2026-08-07

---

## Compression

**1.4, derived.** Reproduce with `python scripts/derive_compression.py`.

`compression_ratio` was the last invented number in the model: the
`event_driven` profile asserted 4.0 with nothing behind it. Deriving it gives
**1.44** — the invention was nearly three times too optimistic.

### Method

Take a position record at the field widths declared in `constants.yaml`, then
re-encode it as zigzag + LEB128 varint deltas from its predecessor. The width of
each delta follows from how much the quantity can change between two fixes,
which follows from vehicle speed and acquisition period. Zigzag and LEB128 are
defined encodings and the distance-per-degree figure is geometry, so every step
is checkable.

At 1e-7 degree resolution, 30 s, 130 km/h:

| field | raw | delta |
|---|---|---|
| timestamp | 8 B | 3 B |
| latitude | 4 B | 3 B |
| longitude | 4 B | 3 B |
| altitude | 2 B | 1 B |
| speed | 2 B | 2 B |
| heading | 2 B | **3 B** |
| satellites | 1 B | 1 B |
| **total** | **23 B** | **16 B** — x1.44 |

The ratio holds at x1.44 for every cadence from 120 s down to 10 s and every
speed up to 130 km/h, and improves to x1.77 at 1 s. The value adopted is 1.4:
the worst case across that grid, rounded down.

### Two things the derivation exposes

**Delta encoding makes some fields worse.** Heading costs 3 bytes as a delta
against 2 bytes raw, because a 90 degree turn at 0.01 degree resolution is 9000
units and zigzagging doubles it. A competent encoder keeps such fields raw and
would beat 1.44. We do not model that.

**The ratio improves with density**, for the reason in the polyline note above:
denser sampling means smaller deltas.

Both errors run the same way — the model understates what a good delta encoder
achieves, and understates it more the denser you sample. Conservative in the
direction that matters.

### Where it is applied

To semantic fields only. Sync words, length prefixes and checksums do not
compress, and an earlier version of the model wrongly divided the whole record —
framing included — by the ratio. Fixed alongside this derivation.

---

## Transport

`ip_tcp_header_bytes` (40), `ack_bytes` (40) and `tcp_handshake_bytes` (120) are
arithmetic on RFC 791 and RFC 793 header sizes, not measurements. The TLS record
overhead (22 bytes: 5-byte header, 16-byte AEAD tag, 1-byte content type) is
likewise structural.

`mss_bytes` (1400) is a conservative choice for cellular paths carrying
tunnelling overhead, not a standard value.

`count_downlink` is marked `to_source`: whether a plan bills the return
direction is contractual. It is exposed as a user toggle because it should be.

---

## Open debts

**The ASTERIX specification was not read.** EUROCONTROL's surveillance data
exchange format would give a second, independent data point on block-level
framing — a data block prefixes its records with a category and a length
indicator. Both candidate PDFs failed to parse automatically. Worth a manual
read to cross-check the SenML derivation.

**TLS handshake sizes are unmeasured.** A device that reconnects over TLS for
every transmission cannot currently be priced: the model raises rather than
guessing. Measure a full and a resumed TLS 1.3 handshake at a receiving socket.

**`session_floor_bytes` is unmeasured.** The per-session billing floor is
contract-specific and rarely documented. The method is in the constants file:
compare operator-reported per-session byte counts against bytes counted at your
own receiving socket, for the same sessions.

**The UBX entry rests on a secondary source.** Read the primary interface
description and promote it.

---

## How to read a Naulon figure

Ratios survive placeholder error far better than absolutes. When the framing
value moved from 50 bytes to 8, the absolute envelope of a heavy goods vehicle
fell by roughly a third — but the *shape* of every conclusion held: the session
count still does not move with acquisition rate, the marginal cost of a position
is still a constant, and fixed per-transmission costs still dominate.

Prefer comparisons. Quote absolutes only for constants marked `sourced` or
`derived`, and say which.
