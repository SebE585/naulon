# Contributing

The most valuable contribution to Naulon is **not code**. It is a number with a
source attached.

## What is most wanted

**A sourced field layout for a documented protocol.** `model/constants.yaml`
currently carries a placeholder for the per-record envelope, flagged
`to_source`. Replacing it with widths taken from published specifications —
with a URL and a consultation date — turns a placeholder into a fact.

**A measured per-session billing floor for a real operator plan.** Compare the
per-session byte counts your operator reports against bytes counted at your own
receiving socket, for the same sessions. The value below which billed volume
stops tracking actual volume is the floor. It is contract-specific, rarely
documented, and it changes conclusions.

**A behavioural profile that does not fit the three we ship.** If your device
follows a pattern that `naive`, `periodic` and `event_driven` do not describe,
that is a gap in the model, not in your device.

## Rules for constants

Every entry carries a `status`:

- `derived` — computable from first principles or a public standard. Fill in
  `basis` with what it is derived from.
- `to_source` — a placeholder. Fill in `source` with a URL and `consulted_on`
  with a date, then promote it.
- `to_measure` — fill in `method` with how to measure it, precisely enough that
  someone else can repeat it.

A constant with no `basis`, `source` or `method` will not be merged. This is the
whole point of the project: a calculator with invented constants is a machine
for producing confident wrong answers.

Vendor and protocol names do not belong in `constants.yaml`. Describe behaviour
and cite public specifications; the model is deliberately vendor-neutral.

## Rules for code

`model/` is the source of truth. No implementation may inline a value that
belongs there.

Any change to the model must be reflected in `model/vectors.json`, and every
implementation must reproduce it exactly:

```bash
cd python && python -m pytest
```

If you change a number in `constants.yaml`, the vectors change with it — that is
expected. Regenerate them in the same commit and say in the message why the
number moved.

## Style

Comments explain why, not what. If a line of the model encodes a claim about
how telematics devices behave, say so in the comment — a reader needs to be able
to disagree with the claim, not just read the arithmetic.
