# Naulon

**Sampling rate is rarely what drives your data bill.**

Naulon models the monthly cellular data envelope of a vehicle telematics fleet
field by field — position, GNSS quality, inertial, vehicle state, heartbeat —
billing each field at the rate of the clock it actually follows, then adding
framing, transport and whatever the operator rounds up.

It answers one question precisely: *if I change this parameter, what happens to
my bill?*

ναῦλον — the fare paid for passage.

---

## Why it exists

Telematics vendors sell sampling cadence as a pricing tier. Buyers accept it
because nobody can check the arithmetic. Naulon makes the arithmetic checkable.

Three results fall out of the model immediately:

- **More positions cost far less than proportionally.** Four times the
  positions is roughly 1.7 times the bytes, because per-transmission costs are
  amortised and only the record count grows.
- **Transmission frequency is nearly free on a persistent session.** Once a
  batch exceeds one MSS, batching stops saving header overhead. Send period
  only becomes expensive when the device reconnects each time, or when the
  operator rounds per session.
- **A device that repeats an unchanged fix pays for it every time.** Emitting
  at 10 Hz on a 1 Hz acquisition means paying ten times to transmit one
  position.

Between the naive and the event-driven profile, with identical sensors and an
identical duty cycle, the model spans more than two orders of magnitude. The
architecture decides the bill, not the sensors.

## Install

```bash
pip install naulon
```

## Use

```bash
naulon --profile periodic --hours 8 --days 22
naulon --profile naive --hours 8 --days 22 --top 5
```

```python
from naulon import estimate

result = estimate({
    "profile": "periodic",
    "device": {"output_rate_hz": 1/30, "fix_rate_hz": 1/30, "send_period_s": 120},
    "fields": {"accel_xyz": False, "hdop": True, "fix_type": True},
    "duty": {"driving_hours_per_day": 8, "driving_days_per_month": 22, "vehicles": 50},
})
print(result.mb_per_month, result.sessions_per_month)
for c in result.contributions[:5]:
    print(f"{c.share:6.1%}  {c.key}")
```

## What it does not do

**It does not ship prices.** M2M tariffs are contractual and not public.
Naulon outputs megabytes and sessions; you supply your own rate, your own
per-session rounding, and it applies them. A tool that guessed your price would
be inventing the most important number in the answer.

**It does not name vendors or protocols.** The model is built from behavioural
archetypes and publicly documented field widths, not from any one product.

## Honesty about the constants

Every constant in `model/constants.yaml` carries a status:

| status | meaning |
|---|---|
| `derived` | computable from first principles or a public standard — the `basis` field says which |
| `to_source` | a placeholder awaiting a citation to a published specification |
| `to_measure` | awaiting empirical measurement — the `method` field says how |

**A constant marked `to_source` or `to_measure` is not a fact.** Every report,
CLI or library, lists the placeholders it leaned on. Do not publish a Naulon
figure as measured until the constants underneath it are sourced.

Ratios are far more robust than absolutes: across the whole plausible range of
the record-envelope placeholder (30–70 bytes), the 120 s → 30 s ratio moves
only between 1.61 and 1.79. Prefer comparisons to single numbers.

## Layout

```
model/          the source of truth — no implementation may inline these values
  constants.yaml    field widths, clocks, encodings, behavioural profiles
  schema.json       input configuration contract
  vectors.json      cross-implementation parity fixtures
python/         reference implementation, library and CLI
```

A JavaScript implementation for the browser calculator will live alongside.
Both read `model/`, both validate against `schema.json`, and both must
reproduce `vectors.json` exactly — which is what makes duplicating a hundred
lines of arithmetic safe.

## Model in one paragraph

Each field is billed at the rate of the clock it follows: `record` (once per
emitted record), `fix` (GNSS acquisition, but billed at the output rate unless
the device deduplicates), `sample` (inertial sampling), `state` (event-driven
unless the device repeats it). Sum over enabled fields, add per-record framing,
divide by the compression ratio, then add transport per transmission: IP and
TCP headers per segment, acknowledgements if the plan bills both directions,
and a handshake if the device reconnects. Driving time and parked time are
computed separately, deliberately — on a fleet that runs eight hours a day, the
other sixteen decide the bill.

## Contributing

The constants file is the asset. The most valuable contribution is not code: it
is **a sourced field layout for a documented protocol**, or **a measured
per-session billing floor for a real operator plan**. See `CONTRIBUTING.md`.

## Licence

Code: Apache-2.0. Model data in `model/`: CC-BY-4.0. See `LICENSE` and
`LICENSE-DATA`.
