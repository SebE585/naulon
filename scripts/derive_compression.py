#!/usr/bin/env python3
"""Derive the delta-encoding compression ratio from first principles.

`compression_ratio` was the last invented number in the model: the event_driven
profile asserted 4.0 with nothing behind it. This script replaces the assertion
with arithmetic.

Method. Take a position record's fields at the widths declared in
constants.yaml. Encode the same record as deltas from its predecessor, zigzagged
and LEB128 varint-encoded (the standard binary varint, 7 payload bits per byte).
The width of each delta follows from how much the quantity can change between
two fixes, which follows from the vehicle speed and the acquisition period.

Everything here is checkable: zigzag and LEB128 are defined encodings, and the
distance-per-degree figures are geometry.

    python scripts/derive_compression.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from naulon import load_constants  # noqa: E402

# One degree of latitude is very close to 111 320 m. Longitude shrinks with
# latitude, but using the latitude figure for both is the conservative choice:
# it makes deltas look larger, so the derived ratio understates the gain.
METRES_PER_DEGREE = 111_320.0

# Reference conditions. Motorway speed is the worst case for delta encoding,
# because it produces the largest displacement between two fixes.
SPEEDS_M_S = {"urban 50 km/h": 13.9, "road 90 km/h": 25.0, "motorway 130 km/h": 36.1}
ACQUISITION_PERIODS_S = (120, 30, 10, 1)
REFERENCE_SPEED = "motorway 130 km/h"

# Fields carried by a position-only record, and how each behaves under delta
# encoding. `delta_span` is the largest plausible change between two records,
# in the field's own units; None means the field is not delta-encodable and
# keeps its raw width.
POSITION_RECORD = [
    #  id,                  raw bytes, unit per LSB,        delta span
    ("timestamp_absolute", 8, None, "cadence"),
    ("latitude", 4, 1e-7, "displacement"),
    ("longitude", 4, 1e-7, "displacement"),
    ("altitude", 2, 1.0, 30.0),          # metres of climb between two fixes
    ("speed", 2, 0.01, 1000.0),          # 10 m/s of change, in 0.01 units
    ("heading", 2, 0.01, 9000.0),        # 90 degrees of turn, in 0.01 units
    ("satellites", 1, None, None),       # not delta-encoded
]


def zigzag(value: int) -> int:
    """Map signed to unsigned so that small negatives stay small."""
    return 2 * value if value >= 0 else -2 * value - 1


def varint_bytes(value: int) -> int:
    """LEB128 width: 7 payload bits per byte."""
    encoded = zigzag(value)
    width = 1
    while encoded >= 128:
        encoded >>= 7
        width += 1
    return width


def delta_record_bytes(period_s: float, speed_m_s: float, lat_lon_lsb: float) -> tuple[int, list]:
    """Width of one position record encoded as deltas from its predecessor."""
    displacement_m = speed_m_s * period_s
    displacement_units = int(displacement_m / (lat_lon_lsb * METRES_PER_DEGREE))

    breakdown = []
    total = 0
    for name, raw_bytes, _lsb, span in POSITION_RECORD:
        if span is None:
            width = raw_bytes                                   # carried as-is
        elif span == "cadence":
            width = varint_bytes(int(period_s * 1000))          # inter-record time, ms
        elif span == "displacement":
            width = varint_bytes(displacement_units)
        else:
            width = varint_bytes(int(span))
        breakdown.append((name, raw_bytes, width))
        total += width
    return total, breakdown


def raw_record_bytes() -> int:
    return sum(raw for _, raw, _, _ in POSITION_RECORD)


def main() -> int:
    constants = load_constants()
    lsb = 1e-7  # the resolution declared for latitude/longitude in constants.yaml
    raw = raw_record_bytes()

    print("Delta encoding of a position record, derived")
    print(f"Raw record: {raw} bytes at {lsb:g} degree resolution\n")

    print(f"{'speed':<20}" + "".join(f"{f'{p} s':>12}" for p in ACQUISITION_PERIODS_S))
    print("-" * (20 + 12 * len(ACQUISITION_PERIODS_S)))
    worst = 99.0
    for label, speed in SPEEDS_M_S.items():
        cells = ""
        for period in ACQUISITION_PERIODS_S:
            encoded, _ = delta_record_bytes(period, speed, lsb)
            ratio = raw / encoded
            worst = min(worst, ratio)
            cells += f"{f'{encoded} B  x{ratio:.2f}':>12}"
        print(f"{label:<20}{cells}")

    print(f"\nWorst case across the grid: x{worst:.2f}")
    print("The ratio improves as acquisition gets denser, because the deltas get")
    print("smaller. Densifying is cheaper per position than this model assumes.\n")

    period = 30
    encoded, breakdown = delta_record_bytes(period, SPEEDS_M_S[REFERENCE_SPEED], lsb)
    print(f"Field by field at {period} s, {REFERENCE_SPEED}:")
    print(f"  {'field':<22}{'raw':>6}{'delta':>7}")
    for name, raw_b, width in breakdown:
        print(f"  {name:<22}{raw_b:>5} B{width:>6} B")
    print(f"  {'TOTAL':<22}{raw:>5} B{encoded:>6} B   x{raw / encoded:.2f}")

    current = constants["profiles"]["event_driven"]["device"]["compression_ratio"]
    print(f"\nconstants.yaml event_driven.compression_ratio = {current}")
    print(f"Conservative derived value: {worst:.1f} (worst case, motorway, coarsest cadence)")
    print()
    print("Note: this ratio applies to semantic fields only. Sync words, length")
    print("prefixes and checksums do not compress, so the model must not apply it")
    print("to record framing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
