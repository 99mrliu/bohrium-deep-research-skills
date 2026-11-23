# Run record — quantity-ledger (SYNTHETIC example, not formal test results)

Everything in `examples/` is synthetic: fabricated inputs exercising parser,
conversion and review paths. The outputs in `synthetic-output/` were generated
by actually running the skill locally; they are example artifacts, not
platform case results.

## Commands actually run

```bash
# 1. end-to-end run (relative paths, stdlib python3 only)
python3 scripts/quantity_ledger.py \
  --case examples/synthetic-case.json --task examples/synthetic-task.md \
  --work scratch/work --out examples/synthetic-output        # exit 0

# 2. determinism: identical second run, byte-level diff of all 12 outputs
python3 scripts/quantity_ledger.py \
  --case examples/synthetic-case.json --task examples/synthetic-task.md \
  --work scratch/work2 --out scratch/run2                    # exit 0
diff -r examples/synthetic-output scratch/run2               # no differences

# 3. invalid input: malformed JSON case -> honest input_error
python3 scripts/quantity_ledger.py \
  --case examples/invalid/broken-case.json --task examples/synthetic-task.md \
  --work scratch/w-inv --out examples/invalid-output         # exit 2
#    result.json: status=input_error, JSON parse error message, only
#    result.json + audit.md as artifacts (partial-state contract)

# 4. invalid input: nonexistent case file -> exit 2, status=input_error
# 5. empty CSV case -> exit 0, status=partial, anomaly empty_table /
#    no_records_found, all output tables written empty (headers only)

# 6. target_units override smoke test
#    {"target_units": {"pressure": "bar", "band_gap": "kg"}}
#    1013.25 hPa -> 1.01325 bar (clean); 1.1 eV -> review
#    (incompatible_target_unit), raw value preserved
```

## Verified correct in the generated outputs (manual inspection)

| record | input | result |
|---|---|---|
| s01 | `1.5–2.5 eV` | range low/high `2.403264951E-19/4.005441585E-19 J`; midpoint only in `std_midpoint_derived` |
| s02/s10 | `0.98 ± 0.02 g/cm^3` | ± split: value 980, unc 20 (separate column), derived bounds 960/1000 flagged; both flagged `duplicate_group=DUP001`, **not merged** |
| s03 | `3.2×10⁻⁴ mol L−1` | scientific notation + Unicode minus → `0.32 mol m^-3` |
| s04 | `1.2 mg/L` (embedded unit) | unit split from value (rule `LEX.embedded_unit`) → `0.0012 kg m^-3` |
| s05/s14 | `350 °C`, `−5–−2 °C` | affine: 623.15 K; range 268.15–271.15 K, offset applied per bound |
| s06 | `120 ppm` | dimensionless `0.00012`, no fabricated concentration conversion |
| s07 | `12.3.4` | `malformed_number` → review, raw kept |
| s08 | `quatloo/mol` | `unknown_unit` → review, raw kept |
| s09, R0017 | empty value | `missing_value`; std columns empty, never imputed |
| s11 | `1,75 kPa` | decimal comma → `1750 Pa` |
| s12 | `1,234 nm` | `ambiguous_decimal_comma` → review (not guessed) |
| s13 | `760 Torr` | `101325 Pa`, ledger `rounded_inexact=true` (101325/760 is non-terminating) |
| s15 | `−1 234.5 mg` (Unicode minus + thin space) | `-0.0012345 kg` |
| R0016 | `50.5(4) J mol−1 K−1` | parenthesis uncertainty → value 50.5, unc 0.4, derived 50.1/50.9 |
| contract | `bibliography_of_papers` | `null` + listed in `unresolved` (no rule maps it; nothing invented) |

Ledger rows carry rule ids (`U.eV|U.J|UC.affine_linear`, `P.milli|U.g|U.L|U.power^-1|…`),
formula, source/target factor+offset, multiplier+offset, precision policy and
input coordinates (`examples/synthetic-case.json#$.records[0]`, `…-extra.csv#row2`).

## Fixes made during inspection

1. °C→K was wrongly rejected (`affine/absolute mismatch`) — removed; affine
   source to linear target of the same dimension is the canonical case.
2. Comma-containing integer parts (`1.234,56`, `1,234,567`) were rejected by
   the token regex — grammar widened, disambiguation still in
   `decimal_from_numeric`.
3. Decimal rendering normalized (no 80-digit trailing-zero noise; scientific
   notation only outside 1e-9…1e21).
4. Contract keys must not be filled by matching free-text descriptions —
   `bibliography_of_papers` now correctly stays `null`/`unresolved`.
5. Embedded-record coordinates now carry the case-file prefix, fixing
   per-source record counts.
