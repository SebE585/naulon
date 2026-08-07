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

**`batch_framing_bytes` has no source.** No publicly specified batching
telematics protocol has been located and read for this value. This is the case
that matters most for the separability argument, because batching is precisely
what decouples transmission count from position count. Known and unresolved.

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
