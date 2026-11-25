# Decimal arithmetic and rounding policy

No binary floating-point arithmetic participates in number parsing or conversion. Numeric tokens become `decimal.Decimal`; conversion runs under local decimal precision 60. JSON output serializes calculated Decimal values as strings and is written with `allow_nan=false`.

The actual case may set:

```json
{"rounding": {"mode": "significant_figures", "digits": 6}}
```

or:

```json
{"rounding": {"mode": "decimal_places", "places": 2}}
```

`decimal_places` uses a decimal-place quantum; `significant_figures` uses a quantum derived from the value's adjusted exponent. `digits`, `significant_figures`, `places`, and `decimal_places` are accepted amount keys. A field-level `rounding` overrides the global default. Default mode is `significant_figures`, 12 digits. Mode `none` retains the precision-60 result. Supported digits/places are 0–50, with at least one significant digit for significant-figure mode.

Rounding is ROUND_HALF_EVEN and applies independently to each central/interval value and the uncertainty magnitude **after conversion**, never to raw values before conversion. Formatting is fixed decimal, trailing fractional zeros are removed, and negative zero becomes `0`. The ledger records mode, digits/places, and tie rule for each changed cell.

Example with six significant figures:

```text
raw:      1 mmol L^-1 min^-1
formula:  raw * (source.scale / target.scale) + 0 - 0
value:    multiplier and rounded value are calculated in Decimal precision 60
rounded:  16.6667 µmol L^-1 s^-1
```

This is a transparent deterministic display policy, not a metrological uncertainty-estimation algorithm. It does not infer confidence from the number of typed digits. Raw lexeme, raw uncertainty and the trace remain available so a reviewer can select a stricter scientific rounding policy later.
