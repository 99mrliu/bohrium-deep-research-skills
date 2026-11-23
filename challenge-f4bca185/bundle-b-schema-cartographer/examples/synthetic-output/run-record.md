# Run record — synthetic example (NOT an official case answer)

Everything in `examples/synthetic-input/` is **invented demonstration data** and every file in
this directory is **example output**. These artifacts demonstrate the interface and semantics
of the tool; they are not official test cases, whiteboards, or expected answers.

## How these artifacts were produced

```bash
python3 scripts/schema_cartographer.py \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work <scratch> --out examples/synthetic-output
# exit code 0
```

## What the run actually did (observed numbers from result.json/audit.md)

- 3 sources harvested: `case.json/records` (6 nested-JSON rows), `case.json/material_csv`
  (6 embedded-CSV rows), `case.json:material-batch-c.csv` (4 external-CSV rows) → 16 rows in,
  16 cleaned rows out; no row merged or dropped.
- 28 columns profiled; 25 mapped (exact alias MAP-001; `_UNIT` suffix MAP-002 for `P_MPa`;
  stop-word fuzzy MAP-003 for `conditions.temperature`; component convention MAP-004 for
  `Yield_min/max (%)`; unit-hint disambiguation MAP-005 for `T / K`, confidence 0.995);
  3 unmapped (`Instrument Serial`, `Mystery Column`, `weird_col`) listed with profiles in
  unresolved-schema.json and preserved per row in `unmapped_json`.
- 16 unit conversions (formulas logged: `K = degC * 1 + 273.15`, `MPa = bar * 0.1`), 2 range
  splits (`72-80 %` → low/high, no midpoint), 1 unknown unit (`eVee` → value null, raw kept,
  anomaly UNIT-UNKNOWN), 1 unparseable value (`high` → ANOM-PARSE), 1 out-of-plausible-range
  (`145 %` → flagged, kept), 1 inverted split-column range (80/70 → flagged, kept).
- 12 missing cells kept null (MISS-001; explicit tokens vs absent columns distinguished).
- 3 duplicate groups, all with conflicting re-extractions → `context_value_conflict`,
  high-severity review; exact-agreement subgroups flagged `exact_duplicate_candidate`.
  No automatic merge anywhere.
- output_contract: 9 fields present; `adjudication_workbook` is null and listed in
  `unresolved_contract_fields` (never fabricated).

## Determinism check (second run)

```bash
python3 scripts/schema_cartographer.py --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md --work <scratch2> --out /tmp/schema-cartographer-rerun
# the 8 generated artifacts were then compared byte-for-byte with this directory
# (run-record.md itself is documentation, not a generated artifact): identical.
```

Outputs contain no wall-clock timestamps; run identity is the SHA-256 of case+task inputs.

## Invalid-input checks

| input | exit code | result.json status |
|---|---|---|
| malformed JSON case file | 2 | `input_error` (parse error recorded, audit.md written) |
| valid JSON with zero harvestable records | 2 | `input_error` ("no records" recorded) |
| non-existent case file path | 2 | `input_error` (FileNotFoundError recorded) |

## Full automated harness

`python3 scripts/selfcheck.py` runs all of the above plus contract/cleaning assertions and
prints `[PASS]` lines; final line `SELF-CHECK: PASS`, exit code 0 (last executed: all 18
checks passed).
