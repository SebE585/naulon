"""Naulon cost model.

The whole model is here, and it is deliberately small: a sum of products over
fields, each field billed at the rate of the clock it follows, plus per-record
framing, plus transport, plus what the operator rounds up.

Nothing in this file is a constant. Every number comes from model/constants.yaml.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as _field
from typing import Any

SECONDS_PER_HOUR = 3600
BYTES_PER_MB = 1_000_000


class ModelError(ValueError):
    """Raised when a configuration cannot be priced."""


@dataclass
class Contribution:
    """What one line item costs over a month, for one vehicle."""

    key: str
    family: str
    clock: str
    bytes_per_month: float
    share: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "family": self.family,
            "clock": self.clock,
            "bytes_per_month": round(self.bytes_per_month, 3),
            "share": round(self.share, 6),
        }


@dataclass
class Result:
    """The monthly envelope, and where it comes from."""

    mb_per_month: float
    mb_per_month_billed: float
    sessions_per_month: float
    bytes_driving: float
    bytes_parked: float
    contributions: list[Contribution]
    unsourced: list[str] = _field(default_factory=list)
    cost: float | None = None
    currency: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mb_per_month": round(self.mb_per_month, 3),
            "mb_per_month_billed": round(self.mb_per_month_billed, 3),
            "sessions_per_month": round(self.sessions_per_month, 1),
            "bytes_driving": round(self.bytes_driving, 1),
            "bytes_parked": round(self.bytes_parked, 1),
            "contributions": [c.as_dict() for c in self.contributions],
            "unsourced": self.unsourced,
            "cost": None if self.cost is None else round(self.cost, 2),
            "currency": self.currency,
        }


def _value(entry: Any) -> Any:
    """Constants are either bare values or {value, status, ...} records."""
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return entry


def _unsourced_constants(constants: dict) -> list[str]:
    """Names of constants that are placeholders, not facts.

    A result that leans on one of these is not publishable as measured. The
    caller is expected to surface this list, not swallow it.
    """
    flagged: list[str] = []
    for section in ("transport", "framing", "billing"):
        for name, entry in constants.get(section, {}).items():
            if isinstance(entry, dict) and entry.get("status") in {"to_source", "to_measure"}:
                flagged.append(f"{section}.{name}")
    return sorted(flagged)


def resolve_config(config: dict, constants: dict) -> tuple[dict, dict[str, bool]]:
    """Merge a profile preset with the caller's overrides.

    Returns the effective device parameters and the effective field switches.
    """
    profiles = constants.get("profiles", {})
    name = config.get("profile")
    if name not in profiles:
        raise ModelError(f"unknown profile {name!r}; known: {sorted(profiles)}")
    preset = profiles[name]

    device = dict(preset.get("device", {}))
    device.update(config.get("device", {}))

    fields = {f["id"]: bool(f.get("default", False)) for f in constants["fields"]}
    fields.update({k: bool(v) for k, v in preset.get("fields", {}).items()})
    fields.update({k: bool(v) for k, v in config.get("fields", {}).items()})

    unknown = set(fields) - {f["id"] for f in constants["fields"]}
    if unknown:
        raise ModelError(f"unknown field ids: {sorted(unknown)}")

    if device["output_rate_hz"] > device["sample_rate_hz"]:
        raise ModelError(
            "output_rate_hz exceeds sample_rate_hz: the device would emit records "
            "it has no samples for"
        )
    return device, fields


def _field_rate_hz(clock: str, device: dict) -> float:
    """How many times per second a field on this clock actually goes on the wire.

    This function is the whole point of the model. A field does not cost what
    its width says; it costs its width times the rate of the clock it follows,
    and the naive device puts every clock on the fastest one.
    """
    output = device["output_rate_hz"]
    if clock == "record":
        return output
    if clock == "sample":
        return device["sample_rate_hz"]
    if clock == "fix":
        # Without deduplication the last fix is recopied into every record, so
        # position is billed at the output rate however slowly it is acquired.
        if device.get("dedup_repeated_fix"):
            return min(device["fix_rate_hz"], output)
        return output
    if clock == "state":
        if device.get("repeat_state_each_record"):
            return output
        return device.get("state_events_per_hour", 0) / SECONDS_PER_HOUR
    raise ModelError(f"unknown clock {clock!r}")


def _payload_bytes_per_second(
    constants: dict, device: dict, fields: dict[str, bool]
) -> tuple[float, list[Contribution]]:
    """Semantic payload plus per-record framing, before transport and compression."""
    per_second: list[Contribution] = []
    total = 0.0

    for spec in constants["fields"]:
        if not fields.get(spec["id"]):
            continue
        rate = _field_rate_hz(spec["clock"], device)
        bps = spec["bytes"] * rate
        total += bps
        per_second.append(
            Contribution(key=spec["id"], family=spec["family"], clock=spec["clock"], bytes_per_month=bps)
        )

    framing = _value(constants["framing"]["record_framing_bytes"]) * device["output_rate_hz"]
    total += framing
    per_second.append(
        Contribution(key="record_framing", family="framing", clock="record", bytes_per_month=framing)
    )
    return total, per_second


def _transport_bytes_per_send(constants: dict, device: dict, payload_per_send: float) -> float:
    """Headers, acknowledgements and handshakes for one transmission."""
    tr = constants["transport"]
    header = _value(tr["ip_tcp_header_bytes"])
    mss = _value(tr["mss_bytes"])

    on_wire = payload_per_send + _value(constants["framing"]["batch_framing_bytes"])
    if device.get("tls"):
        on_wire += _value(tr["tls_record_overhead_bytes"])

    segments = max(1, math.ceil(on_wire / mss))
    overhead = segments * header
    if _value(tr["count_downlink"]):
        overhead += segments * _value(tr["ack_bytes"])

    if device.get("session_policy") == "reconnect_per_send":
        overhead += _value(tr["tcp_handshake_bytes"])
        if device.get("tls"):
            resumed = _value(tr["tls_handshake_resumed_bytes"])
            if resumed is None:
                raise ModelError(
                    "transport.tls_handshake_resumed_bytes is unmeasured; a device that "
                    "reconnects for every transmission over TLS cannot be priced until it is"
                )
            overhead += resumed
    return overhead


def _regime_bytes(
    constants: dict,
    device: dict,
    fields: dict[str, bool],
    seconds: float,
) -> tuple[float, float, list[Contribution]]:
    """Bytes and session count over `seconds` of the full-stream regime."""
    payload_ps, contributions = _payload_bytes_per_second(constants, device, fields)
    payload_ps /= device.get("compression_ratio", 1.0)

    send_period = device["send_period_s"]
    sends = seconds / send_period
    payload_per_send = payload_ps * send_period
    transport_per_send = _transport_bytes_per_send(constants, device, payload_per_send)

    for c in contributions:
        c.bytes_per_month = c.bytes_per_month * seconds / device.get("compression_ratio", 1.0)
    contributions.append(
        Contribution(
            key="transport",
            family="transport",
            clock="send",
            bytes_per_month=transport_per_send * sends,
        )
    )
    total = payload_ps * seconds + transport_per_send * sends
    return total, sends, contributions


def _heartbeat_bytes(constants: dict, device: dict, seconds: float) -> tuple[float, float]:
    """A parked device that behaves still pays to say it is there."""
    period = device.get("heartbeat_period_s")
    if not period:
        return 0.0, 0.0
    beats = seconds / period
    payload = _value(constants["framing"]["record_framing_bytes"])
    per_beat = payload + _transport_bytes_per_send(constants, device, payload)
    return per_beat * beats, beats


def compute(config: dict, constants: dict) -> Result:
    """Price one month of one fleet.

    Driving time and parked time are computed separately and deliberately: on a
    fleet that runs six hours a day, the other eighteen decide the bill.
    """
    device, fields = resolve_config(config, constants)
    duty = config["duty"]
    vehicles = duty.get("vehicles", 1)

    driving_s = duty["driving_hours_per_day"] * SECONDS_PER_HOUR * duty["driving_days_per_month"]
    month_s = 24 * SECONDS_PER_HOUR * 30
    parked_s = max(0.0, month_s - driving_s)

    bytes_driving, sends_driving, contributions = _regime_bytes(constants, device, fields, driving_s)

    if device.get("emit_when_parked"):
        bytes_parked, sends_parked, parked_contrib = _regime_bytes(constants, device, fields, parked_s)
        by_key = {c.key: c for c in contributions}
        for c in parked_contrib:
            by_key[c.key].bytes_per_month += c.bytes_per_month
    else:
        bytes_parked, sends_parked = _heartbeat_bytes(constants, device, parked_s)
        contributions.append(
            Contribution(key="heartbeat", family="service", clock="service", bytes_per_month=bytes_parked)
        )

    total_bytes = (bytes_driving + bytes_parked) * vehicles
    sessions = sends_driving + sends_parked
    if device.get("session_policy") != "reconnect_per_send":
        # One session per driving day, plus one for the parked stretch between.
        sessions = duty["driving_days_per_month"] * 2
    sessions *= vehicles

    for c in contributions:
        c.bytes_per_month *= vehicles
        c.share = c.bytes_per_month / total_bytes if total_bytes else 0.0
    contributions.sort(key=lambda c: c.bytes_per_month, reverse=True)

    tariff = config.get("tariff") or {}
    granularity = tariff.get("billing_granularity_bytes")
    if granularity:
        per_session = total_bytes / sessions if sessions else 0.0
        billed_bytes = sessions * math.ceil(per_session / granularity) * granularity
    else:
        billed_bytes = total_bytes

    cost = None
    price_mb = tariff.get("price_per_mb")
    if price_mb is not None:
        cost = billed_bytes / BYTES_PER_MB * price_mb
        cost += sessions * (tariff.get("price_per_session") or 0.0)

    return Result(
        mb_per_month=total_bytes / BYTES_PER_MB,
        mb_per_month_billed=billed_bytes / BYTES_PER_MB,
        sessions_per_month=sessions,
        bytes_driving=bytes_driving * vehicles,
        bytes_parked=bytes_parked * vehicles,
        contributions=contributions,
        unsourced=_unsourced_constants(constants),
        cost=cost,
        currency=tariff.get("currency", "EUR") if cost is not None else None,
    )
