# Decimal mathematics and rounding

All operands enter `Decimal` from JSON strings, never binary floats. The engine uses local decimal precision 50 and rejects NaN and Infinity. JSON numeric tokens are rejected for ledger values; use strings such as `"40"` or `"0.025"` to preserve the intended decimal representation.

## Safe operations

For decimal operands `a`, `b`, and a list `xs`:

| Operation | Definition | Required condition |
|---|---|---|
| `percent_relative_change` | signed: `100 * (b-a) / abs(a)`; reduction: `100 * (a-b) / abs(a)` | `a != 0`; operands must share a unit |
| `percentage_point_difference` | signed: `b-a`; reduction: `a-b` | both operands have unit `percent` or `percentage` |
| `ratio` | `b/a` by default; `a/b` when `ratio_order` is `initial_over_final` | denominator nonzero; operands share a unit |
| `difference` | signed: `b-a`; reduction: `a-b` | operands share a unit |
| `product` | product of `xs` | at least one operand; unit labels are carried descriptively, not dimensionally solved |
| `sum` | sum of `xs` | at least one operand; all operands share a unit |
| `division` | `a/b` | `b != 0` |

`a` and `b` correspond to `initial` and `final` for changes/differences/ratios, and to `numerator` and `denominator` for division. The exact instantiated formula is saved with each result. No expression parser or `eval` is used.

A 40% error becoming 30% has signed relative change `-25%`, relative reduction `25%`, signed percentage-point difference `-10`, and percentage-point reduction `10`. Do not call a 10 percentage-point change a 10% change.

## Expected value, rounding, and tolerance

Each calculation supplies an independent `expected` decimal string and a tolerance:

- `{"type":"absolute","value":"0.01"}` compares `abs(rounded_actual - expected) <= 0.01`.
- `{"type":"relative","value":"0.001"}` compares the absolute discrepancy to `0.001 * abs(expected)`; a zero expected value is allowed only when actual is exactly zero within absolute zero, so prefer absolute tolerance near zero.

Rounding is explicit: `places` is the number of decimal places and `mode` is one of `ROUND_HALF_UP`, `ROUND_HALF_EVEN`, `ROUND_DOWN`, or `ROUND_UP`. The engine preserves raw and rounded decimal strings. Comparison is against the rounded result. `display_places` is not implicit mathematical precision.

For multiplication/division, units are not silently cancelled. Record a claimed output unit only when justified by the formula. For percent operations, relative results have unit `percent`; percentage-point results have unit `percentage_points`.

## Significant figures and inference

Decimal arithmetic does not establish measurement precision. Retain displayed source precision and mention significant-figure limitations when inputs are rounded. Do not infer CI/error bars/statistical significance from close agreement. Repeated measurements on the same subjects, specimens, or runs are not independent replicates; this engine performs arithmetic, not statistical inference.
