# Synthetic Example Run Record — NOT AN OFFICIAL ANSWER

The files in `examples/synthetic-input` and `examples/synthetic-output` are generated teaching fixtures. They are **synthetic**, are **not** official test cases, are **not** the organizer's whiteboard, and are **not** real experimental measurements. The fake DOI-like strings and material values exist only to exercise dirty-data behavior.

## Command actually run

From the bundle root:

```bash
python3 scripts/lineage_guardian.py \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work examples/synthetic-work \
  --out examples/synthetic-output
```

Observed exit code: `0`.

## Fixture coverage

- UTF-8 BOM in `dirty_records.csv` header.
- Column aliases such as `Material Label`, `Property/Metric`, `Measured Value`, `Temp`, `Duration`, and `Pressure (kPa)`.
- Nested JSON records under `embedded_material.records`, including `Value_kJ` and an overriding cell unit `50 J`.
- Range `25–30 °C`, preserved as min/max rather than a midpoint.
- `1.2 ks` and separate `ks` unit conversion to seconds.
- Duplicate extraction candidates from the same synthetic experiment; all rows remain present.
- Same material/property/value with a different temperature, marked as a context conflict that must not be merged.
- Unknown units `g/100 g water` and `quat`, left unconverted.
- Explicit missing property value, left null and removed from statistical inclusion without deleting the row.
- U+FFFD replacement marker in a notes cell and source-level encoding audit.
- One entirely empty CSV row, excluded from cleaned rows but retained in `raw_snapshot.json`.

## Actual output summary

The generated `result.json` reports:

- `status`: `success`
- `case_id`: `SYNTH-LINEAGE-001`
- sources: `2` (case JSON with nested records, dirty CSV)
- tables: `2`
- raw rows: `11`
- cleaned rows: `10`
- explicitly excluded empty rows: `1`
- unknown-unit rows: `2`
- missing-value rows: `1`
- duplicate groups: `2`
- review items: `13`
- `custom_extension`: `null`
- `unresolved_contract_fields`: `["custom_extension"]`

`success` means the pipeline completed; it does not mean the 13 review items are scientifically resolved.

## Determinism check actually run

The same input was rerun to temporary output/work locations. Byte-for-byte comparison of the substantive artifacts produced:

- `cleaned_rows.csv`: match
- `cleaned_rows.json`: match
- `raw_snapshot.json`: match
- `change_log.jsonl`: match
- `review_queue.json`: match
- `audit_report.md`: match
- `result.json`: match

No timestamp or random value is emitted. Source paths inside the input directory are recorded relative to the case directory; external paths, if any, remain explicit run facts and should be excluded from cross-machine byte comparison.

## Failure-path checks actually run

1. A malformed synthetic `case.json` was run separately. Exit code was `1`; final `result.json` had `status=input_error`, retained core fields (`case_id`, `status`, `sources`, `uncertainty`, `change_records`, `artifacts`), recovered the complete `output_contract` fragment, set unknown `mystery` to `null`, and listed it in `unresolved_contract_fields`.
2. A synthetic CSV containing an invalid UTF-8 byte was run separately. Exit code was `0`; final status was `partial`, source decode status was `recovered_with_replacement`, and rules `R-ANM-001`/`R-ANM-002` were generated. No lost character was guessed.

## How to inspect lineage

Example: find `1.2 ks` in `change_log.jsonl`; it has rule `R-UNIT-008` for value/unit splitting and `R-UNIT-002` with formula `value * 1000`. Use that record's `row_id` and `row_fingerprint` in `raw_snapshot.json` to recover the original CSV row, header occurrence, physical line range, and raw cell. Then find the same `row_id` in `cleaned_rows.json` and `cleaned_rows.csv`.
