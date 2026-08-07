#!/usr/bin/env python3
"""Freeze the send period, vary the acquisition rate, watch what happens.

This is the separability theorem made concrete. A position-only feed with
transmissions locked at one every two minutes; only the acquisition rate moves.

The point is not the percentage. The point is that the marginal cost of one
additional position is a constant, and a small one, because everything
expensive is paid per transmission and the transmission count does not change.

Three duty profiles are included because the same absolute delta reads very
differently as a percentage depending on how much the vehicle runs, which is
exactly why percentages are the wrong unit here.

Run:
    python scenarios/frozen_send_period.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from naulon import compute, load_constants  # noqa: E402

DUTY_PROFILES = {
    "heavy goods": {"driving_hours_per_day": 7, "driving_days_per_month": 22, "vehicles": 1},
    "light commercial": {"driving_hours_per_day": 4, "driving_days_per_month": 22, "vehicles": 1},
    "private car": {"driving_hours_per_day": 1.5, "driving_days_per_month": 30, "vehicles": 1},
}

# A position-only feed: no inertial stream, minimal quality fields. This is the
# configuration a fleet uses when it wants trajectories, not driver behaviour.
FIELDS = {
    "accel_xyz": False,
    "gyro_xyz": False,
    "magneto_xyz": False,
    "satellites": True,
    "hdop": False,
    "fix_type": False,
}

SEND_PERIOD_S = 120
ACQUISITION_PERIODS_S = (120, 60, 30, 20, 10, 5, 1)
ENVELOPE_RANGE_BYTES = (30, 40, 50, 60, 70)
REFERENCE_PROFILE = "heavy goods"


def positions_per_month(duty: dict, acquisition_period_s: float) -> float:
    driving_s = duty["driving_hours_per_day"] * 3600 * duty["driving_days_per_month"]
    return driving_s / acquisition_period_s


def run(constants: dict, duty: dict, acquisition_period_s: float):
    """One configuration. The send period never moves."""
    device = {
        "output_rate_hz": 1 / acquisition_period_s,
        "fix_rate_hz": 1 / acquisition_period_s,
        "send_period_s": SEND_PERIOD_S,
        "session_policy": "persistent",
        "dedup_repeated_fix": True,
        "emit_when_parked": False,
        "tls": False,
    }
    return compute(
        {"profile": "periodic", "device": device, "fields": FIELDS, "duty": dict(duty)},
        constants,
    )


def table_by_duty(constants: dict) -> None:
    print(f"Position-only feed, send period frozen at {SEND_PERIOD_S} s")
    print("Only the acquisition rate varies. The session count never does.")
    print()
    header = f"{'duty profile':<18}" + "".join(f"{f'{p} s':>10}" for p in ACQUISITION_PERIODS_S)
    print(header + f"{'sessions':>10}")
    print("-" * len(header + f"{'sessions':>10}"))
    for label, duty in DUTY_PROFILES.items():
        cells = ""
        sessions = 0.0
        for period in ACQUISITION_PERIODS_S:
            result = run(constants, duty, period)
            sessions = result.sessions_per_month
            cells += f"{result.mb_per_month:>10.2f}"
        print(f"{label:<18}{cells}{sessions:>10.0f}")
    print()
    print("MB per vehicle per month.")


def table_percentages(constants: dict) -> None:
    """Why the percentage is the wrong unit.

    The same absolute delta is a large percentage on a vehicle that barely runs
    and a small one on a vehicle that runs all day, because the baseline is
    dominated by fixed costs paid whether it moves or not.
    """
    print()
    print("The same change, read as a percentage")
    print()
    print(f"{'duty profile':<18}{'120 -> 30 s':>14}{'absolute':>14}")
    for label, duty in DUTY_PROFILES.items():
        base = run(constants, duty, 120).mb_per_month
        dense = run(constants, duty, 30).mb_per_month
        print(f"{label:<18}{(dense / base - 1) * 100:>13.0f}%{f'+{dense - base:.2f} MB':>14}")
    print()
    print("Same physics, three different headlines. Quote the absolute.")


def table_marginal_cost(base_constants: dict) -> None:
    """The marginal cost of one position, and how much the placeholder moves it."""
    duty = DUTY_PROFILES[REFERENCE_PROFILE]
    print()
    print(f"Marginal cost of one additional position ({REFERENCE_PROFILE})")
    print("(sensitivity to record_framing_bytes, which is still a placeholder)")
    print()
    print(f"{'envelope':>10} {'marginal':>12} {'120 -> 30 s':>18}")
    n_base = positions_per_month(duty, 120)
    n_dense = positions_per_month(duty, 30)
    for envelope in ENVELOPE_RANGE_BYTES:
        constants = copy.deepcopy(base_constants)
        constants["framing"]["record_framing_bytes"]["value"] = envelope
        delta_mb = run(constants, duty, 30).mb_per_month - run(constants, duty, 120).mb_per_month
        marginal = delta_mb * 1e6 / (n_dense - n_base)
        print(f"{envelope:>8} B {marginal:>10.1f} B {f'+{delta_mb:.2f} MB/veh/mo':>18}")
    print()
    print("A constant, and a small one. It does not depend on how often you transmit.")


def table_composition(constants: dict) -> None:
    """Where the volume actually goes at the baseline rate.

    Worth running before optimising anything: the position fields themselves are
    usually a rounding error next to the fixed costs.
    """
    duty = DUTY_PROFILES[REFERENCE_PROFILE]
    print()
    print(f"Composition at {ACQUISITION_PERIODS_S[0]} s acquisition ({REFERENCE_PROFILE})")
    print()
    result = run(constants, duty, ACQUISITION_PERIODS_S[0])
    for contribution in result.contributions:
        if contribution.bytes_per_month <= 0:
            continue
        print(
            f"  {contribution.share * 100:>5.1f}%  {contribution.key:<22}"
            f" {contribution.bytes_per_month / 1e6:>7.3f} MB"
        )
    position_share = sum(
        c.share for c in result.contributions if c.family in {"position", "gnss_quality"}
    )
    print()
    print(f"  Position and quality fields together: {position_share * 100:.1f}% of the volume.")
    print("  The parked-time heartbeat period is an assumption here, not a")
    print("  measurement. Whatever its real value, the structure holds: fixed")
    print("  per-transmission costs dominate, payload does not.")


def main() -> int:
    constants = load_constants()
    table_by_duty(constants)
    table_percentages(constants)
    table_marginal_cost(constants)
    table_composition(constants)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
