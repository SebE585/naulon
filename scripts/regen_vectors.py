#!/usr/bin/env python3
"""Regenerate model/vectors.json from the current constants.

Run this whenever a value in constants.yaml changes, in the same commit as the
change, and say in the commit message why the number moved.

    python scripts/regen_vectors.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from naulon import compute, load_constants  # noqa: E402

FLEET_DUTY = {"driving_hours_per_day": 8, "driving_days_per_month": 22, "vehicles": 1}
HGV_DUTY = {"driving_hours_per_day": 7, "driving_days_per_month": 22, "vehicles": 1}

POSITION_ONLY = {
    "accel_xyz": False,
    "gyro_xyz": False,
    "magneto_xyz": False,
    "satellites": True,
    "hdop": False,
    "fix_type": False,
}


def position_feed(session_policy: str, send_period_s: float, acquisition_s: float) -> dict:
    return {
        "profile": "periodic",
        "device": {
            "output_rate_hz": 1 / acquisition_s,
            "fix_rate_hz": 1 / acquisition_s,
            "send_period_s": send_period_s,
            "session_policy": session_policy,
            "dedup_repeated_fix": True,
            "emit_when_parked": False,
            "tls": False,
        },
        "fields": dict(POSITION_ONLY),
        "duty": dict(HGV_DUTY),
    }


CASES: list[tuple[str, str, dict]] = [
    ("periodic_defaults", "Profile defaults, no overrides.",
     {"profile": "periodic", "duty": dict(FLEET_DUTY)}),
    ("naive_defaults", "The pathological device: repeats its fix, never stops, reconnects.",
     {"profile": "naive", "duty": dict(FLEET_DUTY)}),
    ("event_driven_defaults", "Event-driven baseline.",
     {"profile": "event_driven", "duty": dict(FLEET_DUTY)}),
    ("position_only_120s", "Position-only feed, one fix every 120 s.",
     {"profile": "periodic",
      "device": {"output_rate_hz": 1 / 120, "fix_rate_hz": 1 / 120, "send_period_s": 120},
      "fields": dict(POSITION_ONLY), "duty": dict(FLEET_DUTY)}),
    ("position_only_30s", "Same feed at 30 s. Four times the positions.",
     {"profile": "periodic",
      "device": {"output_rate_hz": 1 / 30, "fix_rate_hz": 1 / 30, "send_period_s": 120},
      "fields": dict(POSITION_ONLY), "duty": dict(FLEET_DUTY)}),
    ("repeated_fix_10hz", "10 Hz output on a 1 Hz fix, no deduplication.",
     {"profile": "periodic",
      "device": {"output_rate_hz": 10, "fix_rate_hz": 1, "dedup_repeated_fix": False},
      "duty": dict(FLEET_DUTY)}),
    ("fleet_of_50", "Linearity check.",
     {"profile": "periodic", "duty": {**FLEET_DUTY, "vehicles": 50}}),
    ("unitary_emission_120s",
     "One frame per position, a session per transmission. Cost follows the event count.",
     position_feed("reconnect_per_send", 120, 120)),
    ("unitary_emission_30s",
     "Same device, four times the positions. Four times the sessions.",
     position_feed("reconnect_per_send", 30, 30)),
    ("batched_emission_120s",
     "Positions grouped into a persistent session. Baseline.",
     position_feed("persistent", 120, 120)),
    ("batched_emission_30s",
     "Four times the positions, same session count. Only payload grows.",
     position_feed("persistent", 120, 30)),
    ("ascii_regime_120s",
     "Same position feed in a text protocol. The framing regime, not the cadence, is the difference.",
     {**position_feed("persistent", 120, 120),
      "device": {**position_feed("persistent", 120, 120)["device"],
                 "framing_regime": "ascii_delimited"}}),
]


def main() -> int:
    constants = load_constants()
    document = {
        "note": (
            "Cross-implementation parity fixtures. Every implementation must reproduce "
            "these outputs exactly. They pin behaviour; they do not prove correctness."
        ),
        "constants_version": constants["version"],
        "vectors": [],
    }
    for name, description, config in CASES:
        result = compute(config, constants)
        document["vectors"].append({
            "name": name,
            "description": description,
            "config": config,
            "expect": {
                "mb_per_month": round(result.mb_per_month, 6),
                "mb_per_month_billed": round(result.mb_per_month_billed, 6),
                "sessions_per_month": round(result.sessions_per_month, 6),
                "bytes_driving": round(result.bytes_driving, 3),
                "bytes_parked": round(result.bytes_parked, 3),
            },
        })
        print(f"  {name:<24} {result.mb_per_month:>10.3f} MB")

    path = ROOT / "model" / "vectors.json"
    path.write_text(json.dumps(document, indent=2) + "\n")
    print(f"\nwrote {len(document['vectors'])} vectors to {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
