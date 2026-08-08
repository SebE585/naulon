"""Behavioural tests.

These assert the properties the model exists to demonstrate. If one of them
breaks, the argument breaks with it.
"""

from __future__ import annotations

import copy

import pytest

from naulon import compute, load_constants
from naulon.model import ModelError

DUTY = {"driving_hours_per_day": 6, "driving_days_per_month": 22, "vehicles": 1}


@pytest.fixture(scope="module")
def constants():
    return load_constants()


def envelope(constants, **overrides):
    config = {"profile": overrides.pop("profile", "periodic"), "duty": dict(DUTY)}
    if overrides:
        config["device"] = overrides
    return compute(config, constants).mb_per_month


def test_faster_acquisition_costs_far_less_than_proportionally(constants):
    """Six times more positions does not cost six times more.

    The record envelope and the transport headers are paid per transmission,
    not per position, so raising the acquisition rate while keeping the same
    send period is nearly free. This is the central claim.
    """
    slow = envelope(constants, output_rate_hz=1 / 120, fix_rate_hz=1 / 120, send_period_s=120)
    fast = envelope(constants, output_rate_hz=1 / 20, fix_rate_hz=1 / 20, send_period_s=120)
    assert fast > slow
    assert fast / slow < 3.0, "six times the data should not cost six times the bytes"


def test_send_period_is_free_on_a_persistent_session(constants):
    """Counter-intuitive, and it survives scrutiny.

    Once a batch exceeds one MSS, batching stops saving header overhead: you
    pay one header per segment either way. With a persistent session and no
    per-session rounding, how often you transmit costs essentially nothing.
    What costs is how many records you produce.
    """
    batched = envelope(constants, output_rate_hz=1 / 20, fix_rate_hz=1 / 20, send_period_s=120)
    immediate = envelope(constants, output_rate_hz=1 / 20, fix_rate_hz=1 / 20, send_period_s=20)
    assert immediate == pytest.approx(batched, rel=0.02)


def test_send_period_dominates_when_the_device_reconnects(constants):
    """The send period only becomes expensive when each transmission carries a
    fixed cost: a handshake, or a billing floor."""
    common = {
        "output_rate_hz": 1 / 20,
        "fix_rate_hz": 1 / 20,
        "session_policy": "reconnect_per_send",
        "tls": False,
    }
    batched = envelope(constants, **common, send_period_s=120)
    immediate = envelope(constants, **common, send_period_s=20)
    assert immediate > batched


def test_repeated_fix_is_the_redundancy_factor(constants):
    """A device emitting at 10 Hz on a 1 Hz fix pays ten times for one position."""
    deduped = envelope(constants, output_rate_hz=10, fix_rate_hz=1, dedup_repeated_fix=True)
    repeated = envelope(constants, output_rate_hz=10, fix_rate_hz=1, dedup_repeated_fix=False)
    assert repeated > deduped


def test_parked_time_is_not_free(constants):
    """The eighteen hours a van does not move decide the bill."""
    quiet = envelope(constants, profile="periodic", emit_when_parked=False)
    stuck = envelope(constants, profile="periodic", emit_when_parked=True)
    assert stuck > quiet * 3


def test_gnss_quality_fields_are_cheap(constants):
    """The first fields everyone cuts save almost nothing."""
    base = {"profile": "periodic", "duty": dict(DUTY)}
    without = compute(base, constants).mb_per_month
    with_quality = compute(
        {**base, "fields": {"hdop": True, "vdop": True, "pdop": True, "fix_type": True}},
        constants,
    ).mb_per_month
    assert (with_quality - without) / without < 0.10


def test_profiles_are_ordered(constants):
    """naive costs more than periodic, which costs more than event-driven."""
    naive = envelope(constants, profile="naive")
    periodic = envelope(constants, profile="periodic")
    event_driven = envelope(constants, profile="event_driven")
    assert naive > periodic > event_driven


def test_billing_granularity_penalises_small_frequent_sends(constants):
    """Rounding works against the frequent-transmission configuration."""
    config = {
        "profile": "periodic",
        "device": {"send_period_s": 20, "session_policy": "reconnect_per_send", "tls": False},
        "duty": dict(DUTY),
        "tariff": {"billing_granularity_bytes": 1024},
    }
    result = compute(config, constants)
    assert result.mb_per_month_billed > result.mb_per_month


def test_contributions_sum_to_the_total(constants):
    result = compute({"profile": "periodic", "duty": dict(DUTY)}, constants)
    total = sum(c.bytes_per_month for c in result.contributions)
    assert total == pytest.approx(result.mb_per_month * 1e6, rel=1e-9)
    assert sum(c.share for c in result.contributions) == pytest.approx(1.0, rel=1e-9)


def test_fleet_scales_linearly(constants):
    one = compute({"profile": "periodic", "duty": dict(DUTY)}, constants).mb_per_month
    fifty = compute(
        {"profile": "periodic", "duty": {**DUTY, "vehicles": 50}}, constants
    ).mb_per_month
    assert fifty == pytest.approx(one * 50, rel=1e-9)


def test_a_binary_configuration_has_no_placeholders_left(constants):
    """Every constant a default binary configuration touches is now sourced,
    derived or measured. If this breaks, something was added without
    provenance."""
    result = compute({"profile": "periodic", "duty": dict(DUTY)}, constants)
    assert result.unsourced == []


def test_every_constant_has_provenance(constants):
    """No constant may sit in the file without saying where it came from."""
    allowed = {"sourced", "derived", "measured"}
    for section in ("transport", "framing", "compression"):
        for name, entry in constants[section].items():
            if not isinstance(entry, dict):
                continue
            if "regimes" in entry:
                for regime, spec in entry["regimes"].items():
                    assert spec["status"] in allowed, f"{section}.{name}[{regime}]"
            else:
                assert entry["status"] in allowed, f"{section}.{name}"


def test_the_placeholder_alarm_still_works(constants):
    """There is no placeholder left in the file, so the mechanism is tested
    against a synthetic one. A green report must mean 'nothing to flag', never
    'the alarm is broken'."""
    doctored = copy.deepcopy(constants)
    doctored["framing"]["batch_framing_bytes"]["status"] = "to_measure"
    result = compute({"profile": "periodic", "duty": dict(DUTY)}, doctored)
    assert result.unsourced == ["framing.batch_framing_bytes"]

    doctored = copy.deepcopy(constants)
    regimes = doctored["framing"]["record_framing_bytes"]["regimes"]
    regimes["ascii_delimited"]["status"] = "to_source"
    used = compute(
        {"profile": "periodic", "device": {"framing_regime": "ascii_delimited"},
         "duty": dict(DUTY)},
        doctored,
    )
    unused = compute({"profile": "periodic", "duty": dict(DUTY)}, doctored)
    assert used.unsourced == ["framing.record_framing_bytes[ascii_delimited]"]
    assert unused.unsourced == []


def test_downlink_billing_is_a_tariff_clause_not_a_constant(constants):
    """Whether the plan bills acknowledgements is contractual. It has to change
    the answer, and it must not live in constants.yaml."""
    assert "billing" not in constants
    billed = compute(
        {"profile": "periodic", "duty": dict(DUTY), "tariff": {"count_downlink": True}},
        constants,
    ).mb_per_month
    uplink_only = compute(
        {"profile": "periodic", "duty": dict(DUTY), "tariff": {"count_downlink": False}},
        constants,
    ).mb_per_month
    assert uplink_only < billed


def test_framing_regimes_are_an_order_of_magnitude_apart(constants):
    """The finding that killed the single-constant model: a text protocol pays
    several times a binary one for identical semantics."""
    def envelope_for(regime):
        return compute(
            {"profile": "periodic", "device": {"framing_regime": regime}, "duty": dict(DUTY)},
            constants,
        ).mb_per_month

    assert envelope_for("ascii_delimited") > envelope_for("binary_framed")
    assert envelope_for("binary_framed") > envelope_for("bit_packed")


def test_unknown_framing_regime_is_rejected(constants):
    with pytest.raises(ModelError):
        compute(
            {"profile": "periodic", "device": {"framing_regime": "nope"}, "duty": dict(DUTY)},
            constants,
        )


def test_output_faster_than_sampling_is_rejected(constants):
    with pytest.raises(ModelError):
        compute(
            {
                "profile": "periodic",
                "device": {"sample_rate_hz": 1, "output_rate_hz": 10},
                "duty": dict(DUTY),
            },
            constants,
        )


def test_unknown_field_is_rejected(constants):
    with pytest.raises(ModelError):
        compute({"profile": "periodic", "fields": {"nope": True}, "duty": dict(DUTY)}, constants)
