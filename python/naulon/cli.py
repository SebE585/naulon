"""Command line interface.

Reproducible by construction: every reported figure can be regenerated from the
command printed at the top of the report.
"""

from __future__ import annotations

import argparse
import json
import sys

from naulon.loader import load_constants
from naulon.model import ModelError, compute


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="naulon",
        description="Model the monthly cellular data envelope of a vehicle telematics fleet.",
    )
    p.add_argument("--profile", default="periodic", help="naive | periodic | event_driven")

    d = p.add_argument_group("device (overrides the profile)")
    d.add_argument("--sample-rate", type=float, dest="sample_rate_hz")
    d.add_argument("--fix-rate", type=float, dest="fix_rate_hz")
    d.add_argument("--output-rate", type=float, dest="output_rate_hz")
    d.add_argument("--send-period", type=float, dest="send_period_s",
                   help="seconds between transmissions; usually the dominant parameter")
    d.add_argument("--compression", type=float, dest="compression_ratio")
    d.add_argument("--dedup", dest="dedup_repeated_fix", action="store_true", default=None)
    d.add_argument("--no-dedup", dest="dedup_repeated_fix", action="store_false")
    d.add_argument("--emit-when-parked", dest="emit_when_parked", action="store_true", default=None)
    d.add_argument("--no-emit-when-parked", dest="emit_when_parked", action="store_false")

    u = p.add_argument_group("duty cycle")
    u.add_argument("--hours", type=float, default=6.0, help="driving hours per day")
    u.add_argument("--days", type=float, default=22.0, help="driving days per month")
    u.add_argument("--vehicles", type=int, default=1)

    f = p.add_argument_group("fields")
    f.add_argument("--enable", action="append", default=[], metavar="FIELD")
    f.add_argument("--disable", action="append", default=[], metavar="FIELD")

    t = p.add_argument_group("tariff (yours, not ours)")
    t.add_argument("--price-per-mb", type=float)
    t.add_argument("--billing-granularity", type=int,
                   help="per-session rounding unit in bytes")

    p.add_argument("--json", action="store_true", help="emit the full result as JSON")
    p.add_argument("--top", type=int, default=10, help="rows in the contribution table")
    return p


def config_from_args(args: argparse.Namespace) -> dict:
    device = {
        k: getattr(args, k)
        for k in (
            "sample_rate_hz", "fix_rate_hz", "output_rate_hz", "send_period_s",
            "compression_ratio", "dedup_repeated_fix", "emit_when_parked",
        )
        if getattr(args, k) is not None
    }
    fields = {name: True for name in args.enable}
    fields.update({name: False for name in args.disable})

    config: dict = {
        "profile": args.profile,
        "duty": {
            "driving_hours_per_day": args.hours,
            "driving_days_per_month": args.days,
            "vehicles": args.vehicles,
        },
    }
    if device:
        config["device"] = device
    if fields:
        config["fields"] = fields
    tariff = {}
    if args.price_per_mb is not None:
        tariff["price_per_mb"] = args.price_per_mb
    if args.billing_granularity is not None:
        tariff["billing_granularity_bytes"] = args.billing_granularity
    if tariff:
        config["tariff"] = tariff
    return config


def render(result, top: int) -> str:
    lines = [
        f"envelope        {result.mb_per_month:10.2f} MB / month",
        f"  billed        {result.mb_per_month_billed:10.2f} MB / month",
        f"sessions        {result.sessions_per_month:10.0f} / month",
        f"  driving       {result.bytes_driving / 1e6:10.2f} MB",
        f"  parked        {result.bytes_parked / 1e6:10.2f} MB",
    ]
    if result.cost is not None:
        lines.append(f"cost            {result.cost:10.2f} {result.currency}")

    lines += ["", "where it goes", "-------------"]
    for c in result.contributions[:top]:
        if c.bytes_per_month <= 0:
            continue
        lines.append(
            f"  {c.share * 100:5.1f}%  {c.key:<22} {c.family:<14} {c.clock:<7}"
            f" {c.bytes_per_month / 1e6:8.2f} MB"
        )

    if result.unsourced:
        lines += [
            "",
            "WARNING — this result leans on constants that are placeholders, not",
            "measurements. Do not publish it as measured until they are sourced:",
        ]
        lines += [f"  - {name}" for name in result.unsourced]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = config_from_args(args)
    try:
        result = compute(config, load_constants())
    except ModelError as exc:
        print(f"naulon: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"config": config, "result": result.as_dict()}, indent=2))
    else:
        print(render(result, args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
