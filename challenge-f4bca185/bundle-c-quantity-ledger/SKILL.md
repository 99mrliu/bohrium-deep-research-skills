---
name: quantity-ledger
description: Clean and standardize literature extraction records (nested JSON/CSV) with a traceable quantity ledger. Robust Decimal-based number parsing (decimal/comma notation where unambiguous, scientific notation, signs, Unicode minus, thin spaces, en/em dash and tilde ranges, symmetric ± / parenthesis uncertainty kept as a separate field, percent/ppm), composite SI unit algebra (mg L^-1, kg/m^3, mol L−1, J mol−1 K−1, SI prefixes), affine Celsius/Fahrenheit handling, exact-definition pressure/energy/time/temperature conversions, conservative schema-alias normalization, duplicate flagging (never auto-merge), anomaly and review lists, and a per-conversion ledger with rule id, formula, multiplier+offset, precision policy, raw value and input coordinates. Missing or unknown values stay empty and go to review; nothing is imputed or merged automatically.
---

# Quantity Ledger — literature data cleaning & standardization

Focus: **数值语法、复合单位、SI 前缀、区间/不确定度与精度可追溯** for batches of real
literature-extraction records. Generic schema handling (alias normalization,
duplicate flagging, anomaly/review lists) is included only to the extent needed
to deliver a complete, verifiable cleaning run.

## When to use

- A case JSON (and/or referenced CSVs) contains extraction records with messy
  numeric literals (`1,23`, `2.4×10⁻⁴`, `−5–−2`, `3.1 ± 0.2`, `120 ppm`) and
  composite or prefixed units.
- You need a statistics-ready table **plus** the full trail: which rule touched
  which value, at which input coordinates, with what multiplier/offset.
- You must not fabricate: unknown units, ambiguous commas, malformed numbers,
  conflicting aliases and duplicates are routed to `review` instead of guessed.

## Run

```bash
python3 scripts/quantity_ledger.py \
  --case /input/case.json --task /input/task.md \
  --work /app/work --out /app/output
```

All four arguments have these exact defaults and are overridable. Rule tables
default to `references/units.json` / `references/aliases.json` next to the
script and are overridable with `--units` / `--aliases`. Stdlib Python 3.10+
only; `decimal.Decimal` is used for all numeric work — no binary floats.
Exit code 0 on `success`/`partial`, 2 on `input_error`.

A minimal `result.json` (status `partial`) is written **before** ingestion, so
even a crashed or invalid run leaves an honest partial artifact.

## Inputs

- **case**: JSON object or CSV. Nested JSON is walked; lists of scalar-valued
  dicts under keys such as `records`/`rows`/`data`/`extractions` are treated as
  record tables (coordinates like `$.sources[0].records[3]`). Dictionaries with
  `path`/`file`/`filename` values ending in `.csv`/`.json` are loaded as
  additional materials (CSV rows get `file#row<N>` coordinates).
  Optional fields: `case_id`, `output_contract` (dict or list),
  `target_units` (per-metric target unit, `"*"` wildcard).
- **task**: free text; hashed into the audit only.

## Outputs (under `--out`)

| file | content |
|---|---|
| `cleaned.csv` / `cleaned.json` | one row per record: material, metric, conditions, raw value/unit, parse status, original `value`/`uncertainty`/`range_low`/`range_high`, standardized `std_*` columns, `conversion_rule_ids`, `duplicate_group`, `record_status`, `review_reasons`, coordinates, raw record |
| `conversion_ledger.csv/.json` | per conversion: rule id(s), formula, source/target factor+offset, multiplier+offset, precision policy, inexact flag, raw value, input coordinates |
| `anomalies.csv/.json` | missing value, malformed number, ambiguous comma, unknown/ambiguous/incompatible unit, inverted range, garbled encoding, negative absolute temperature, missing material files |
| `review.csv/.json` | everything a human must confirm (all anomalies plus duplicates, conflicts, missing units) with suggested actions |
| `change_log.csv/.json` | every alias rename, value parse, uncertainty split, range parse, unit conversion, duplicate flag — with rule id and coordinates |
| `audit.md` | counts, sources with sha256, errors, uncertainty list, method notes |
| `result.json` | `case_id`, `status` (`success`/`partial`/`input_error`), `summary`, `sources`, `uncertainty`, `change_records`, `artifacts`, plus every top-level `output_contract` key; unfillable keys are `null` and listed in `unresolved` |

Conventions: range midpoints appear **only** in `std_midpoint_derived`;
symmetric-uncertainty bounds appear only in `std_unc_low/high_derived`; ± is
never silently turned into a range. Unknown/incompatible units stay raw.
Empty numeric strings mean "not reported / not parsed" — never zero.

## Rules and references

- `references/units.json` — unit/prefix rules with ids (`U.*`, `P.*`), exact
  rational definitions where they exist (`factor_num/factor_den`), affine
  formulas for °C/°F, ambiguous symbols (`C`, `ppt`), default SI targets.
- `references/lexical-grammar.md` — the exact number grammar and its failure
  modes; `references/cleaning-rules.md` — rule priorities, conflict order,
  anomaly taxonomy, duplicate key; `references/units-and-conversions.md` —
  human-readable conversion table with formulas and exactness notes.

## Limitations (read before trusting output)

- Comma decimals are accepted only where unambiguous; `1,234` always goes to review.
- ppm/% are dimensionless ratios only; converting to mg/L needs density/molar mass and is deliberately not done.
- Conversions assume the unit carries the physical dimension; scientific conflicts (same material+metric, different values) are flagged, not adjudicated.
- Non-SI definitions marked `is_exact=false` (mmHg, psi, inHg, Hartree) are conventional/approximate; `rounded_inexact=true` in the ledger marks inexact Decimal steps (e.g. Torr = 101325/760).
- Duplicate detection flags only identical conservative keys; near-duplicates and cross-paper repeated experiments need human review by design.
- Parsing is line-record based; units embedded in prose sentences without a value column are not recovered.
