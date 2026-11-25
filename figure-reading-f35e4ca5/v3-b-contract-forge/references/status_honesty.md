# Status honesty: success / partial / unable / refused

`status` is a claim about the *deliverable*, and lint enforces it mechanically. Decide
status from the table below; never from optimism.

## Decision table

| status | concrete triggers (ALL must hold) |
|---|---|
| `success` | every required contract field is non-null; every claim-like leaf (numeric `value`) has a locator or a non-empty top-level `sources`; zero unresolved `uncertainty` entries; `case_id` matches the case |
| `partial` | anything was delivered, but: ≥1 required field null (documented or not), OR ≥1 uncertainty entry unresolved, OR a lint downgrade was applied |
| `unable` | no contract field could be filled from shipped materials (e.g. figure unreadable, materials absent); result still carries `case_id`, the contract-shaped skeleton, and full reasons in `uncertainty` |
| `refused` | the task itself is out of scope or unsafe; state why in `uncertainty` |

## The ratchet rule

**Any unresolved uncertainty entry blocks `success`.** An entry is resolved only when it
is an object with `"resolved": true`. Bare strings and entries without the flag are
unresolved. `contract_lint.py` auto-downgrades a `success` that violates this (or that
sits on null required fields) to `partial`, rewrites result.json, and records the
downgrade — so a dishonest status is not merely wrong, it is overwritten.

Also mechanical:
- `case_id` mismatch is fatal (lint exit 1): no status at all is valid until fixed.
- `success` requires locatable claims: numbers without `source`/`locator` siblings and
  an empty top-level `sources` list are lint violations even if every field is filled.

## Worked examples of honest partial statements

Good `uncertainty` entries for a `partial` result:

```json
{"path": "/figure/axes/y/unit", "reason": "y-axis unit not printed; refused to guess", "resolved": false}
```

```json
{"path": "/figure/series[]/data_points", "reason": "only 4 of 11 points digitized within budget; points at x=0,3,6,10 are from table.csv (exact)", "resolved": false}
```

```json
{"path": "/gaps", "reason": "Fig. 2b referenced in caption but pixels not shipped; listed as declared gap, not reconstructed", "resolved": true}
```

An honest `partial` summary line in the result (e.g. inside an answers field or notes):

> "Axes, series trend, and Q1–Q2 are delivered with locators. `statistics.p_value` is
> null: the task requested a test whose inputs are not in the shipped table; I did not
> compute one from digitized pixels. Status is partial for that single field."

What **not** to write:

- `"status": "success"` with any `uncertainty` entry still open — lint will downgrade.
- `"answer": "approximately 42"` with no `evidence` — a claim without a locator.
- Reconstructed values for a figure that was never shipped — that belongs in `gaps`,
  not in the contract fields.
- `"uncertainty": []` when you know something is missing — empty uncertainty is itself
  a claim ("nothing is uncertain"); only assert it when true.
