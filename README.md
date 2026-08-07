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

- **More positions cost far less than proportionally.** One extra position
  costs about 31 bytes in a binary protocol and nothing else — no session, no
  handshake, no billing floor — because those are paid per transmission and the
  transmission count does not move.
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

## The separability theorem

The monthly volume splits into two independent terms:

```
volume =  per_transmission_cost x number_of_transmissions
        + marginal_cost_per_position x number_of_positions
```

The first term is set by the **transmission period**: session setup, handshake,
IP and TCP headers, acknowledgements, per-session billing floor. The second is
set by the **acquisition rate**.

Record framing is a **regime**, not a constant — binary framed (8 B),
bit-packed (4 B), text-delimited (~60 B) — and it is the term that sets the
marginal cost. It is an explicit parameter rather than a hidden assumption.

They are separable. Raising the acquisition rate touches only the second term —
and the marginal cost of one position is a *constant*: its field widths plus
the record envelope, plus a sliver of segment overhead. It does not depend on
how often you transmit.

This is algebra, not measurement, which is what makes it hard to argue with.

Worked across three duty profiles in
`scenarios/frozen_send_period.py` — position-only feed, transmissions locked at
one every two minutes, only the acquisition rate moving:

| duty profile | 120 s | 30 s | 10 s | sessions |
|---|---|---|---|---|
| heavy goods, 7 h/day | 1.12 MB | 1.55 MB | 2.70 MB | unchanged |
| light commercial, 4 h/day | 0.97 MB | 1.21 MB | 1.87 MB | unchanged |
| private car, 1.5 h/day | 0.87 MB | 0.99 MB | 1.33 MB | unchanged |

The marginal cost of one position is **31 bytes** in the binary framing regime,
27 in the bit-packed one, 83 in text. Everything else in those rows is fixed
cost that does not care how often you sample.

Two cautions the numbers make visible:

- **Percentages are the wrong unit.** They depend entirely on the baseline,
  which is dominated by whatever the device does while parked. Going from 120 s
  to 30 s reads as +38 % on a heavy goods vehicle and +15 % on a private car —
  same physics, three different headlines. Quote the marginal cost per
  position, or the absolute delta per vehicle.
- **Check the composition before optimising.** In the heavy goods row, position
  and quality fields together are 6 % of the volume and the parked-time
  heartbeat is 53 %.

The theorem collapses in exactly one arrangement: a device that opens a session
for every single position. The transmission count then *is* the position count,
the two terms merge, and acquisition rate really does drive cost. The vectors
`unitary_emission_*` and `batched_emission_*` price both arrangements side by
side — same vehicle, same feed, a factor of two between them. Which arrangement
a given deployment is in is a configuration property, and the model cannot
guess it: it has to be read off the operator's session counts and mean message
size.

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

**It does not guess.** Every number is sourced, derived from a published
standard, or flagged as a placeholder in the output. Two of the original
invented constants have since been shown wrong by a factor of five and a factor
of three respectively — by the act of sourcing them.

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
| `sourced` | taken from a published specification, with URL and consultation date |
| `derived` | computable from first principles or a public standard — the `basis` field says which |
| `to_source` | a placeholder awaiting a citation to a published specification |
| `to_measure` | awaiting empirical measurement — the `method` field says how |

`RATIONALE.md` documents every value: where it came from, what was cross-checked
against what, and what is still owed.

**A constant marked `to_source` or `to_measure` is not a fact.** Every report,
CLI or library, lists the placeholders it leaned on. Do not publish a Naulon
figure as measured until the constants underneath it are sourced.

This is not theoretical. Version 0.1.0 shipped a single unsourced 50-byte
record envelope; sourcing it against published specifications showed binary
protocols frame a record in 8 bytes, not 50 — five times off, and it had
propagated into every figure here. Nothing had been published as measured,
because every report flagged it. That is what the status field is for.

Prefer ratios to absolutes. When that value moved from 50 to 8, absolute
envelopes fell by about a third while every conclusion held: the session count
still does not move with acquisition rate, and the marginal cost of a position
is still a constant.

## Layout

```
model/          the source of truth — no implementation may inline these values
  constants.yaml    field widths, clocks, encodings, framing regimes, profiles
  schema.json       input configuration contract
  vectors.json      cross-implementation parity fixtures
python/         reference implementation, library and CLI
scenarios/      reproducible worked examples
scripts/        regen_vectors.py, derive_compression.py — rerun after changes
RATIONALE.md    provenance of every constant, and the open debts
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
