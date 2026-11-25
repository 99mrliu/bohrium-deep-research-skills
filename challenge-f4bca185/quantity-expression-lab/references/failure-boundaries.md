# Failure boundaries and field specifications

## Case specification

A direct field→target mapping is sufficient:

```json
{"unit_conversions": {"temperature_c": "K", "rate": "µmol L^-1 s^-1"}}
```

A richer list or mapping entry may use:

```json
{
  "field": "duration",
  "source_unit": "min",
  "target_unit": "s",
  "unit_field": "optional_unit_column",
  "report_missing": true,
  "rounding": {"mode": "decimal_places", "places": 3}
}
```

`unit_conversions`, `conversions`, `quantity_fields`, `unit_targets`, `target_units`, `standardize`, `column_units`, and `fields_to_convert` wrappers are recognized. `field`, `name`, `value_field`, or `column` identifies the source cell. `target_unit`, `to`, `target`, or `canonical_unit` identifies a target; a lone `unit` in a simple rule is the target. `source_unit`, `input_unit`, or `unit_hint` supplies a unit for a numeric-only cell; `unit_field` reads it from the row.

Case rules override the same material-level rules. Per-cell conversion never supersedes a case target with a guessed field meaning. `number_region` and explicit separators obey the same precedence.

## Honest failure behavior

- **Ambiguous decimal/grouping:** leave raw; `ambiguous_decimal`, `ambiguous_grouping`, or `invalid_grouping` review. No locale guess.
- **Unknown unit:** leave raw; `unknown_unit` review. No fuzzy unit match.
- **Missing:** leave empty/null/NA/dash-only text unchanged, never zero. Sparse optional blanks appear in the ledger if their column is present but do not flood the review queue. Set `report_missing: true` (or `required: true`) per field to make missing cells/fields actionable review items.
- **Dimension mismatch:** no arithmetic; `dimension_mismatch` review.
- **Affine misuse, invalid exponent, malformed quantity, negative uncertainty, mixed interval plus uncertainty:** no conversion; stable review code.
- **Unknown canonical dimension in auto mode:** request an explicit target via `no_safe_canonical_unit` review.
- **No records, invalid JSON/JSONL/CSV/TSV, nonexistent case/task/input:** exit code 2. Write all required artifacts when possible with `status: error`, raw error, and no fabricated values.
- **Cell-level compile failures:** preserve other completed rows and return `status: partial`, normally exit code 0 so the honest partial result can be inspected.
- **Unknown output-contract keys:** JSON null with an `unresolved_contract` item. Keys are never silently omitted or filled with guessed content.

All seven artifacts are written before processing, so an interruption cannot masquerade as a successful complete run. The `result.json` `status` distinguishes `success`, `partial`, and `error`. Sources are relative names plus deterministic SHA-256 hashes; cell locators identify the table line or JSON path.

## Deliberate non-goals

Only configured quantity fields, or strings with embedded units in unconfigured auto mode, are changed. Original non-quantity fields and identity columns are not normalized. No duplicate detection, duplicate merging, chemical synonym resolution, cross-source fusion, range plausibility judgment, scientific conflict adjudication, page/PDF inference, OCR, or missing-data imputation is attempted. Repeated row identities remain separate; they are never silently collapsed.

NBSP/thin-space/apostrophe grouping is supported; regular ASCII-space grouping is rejected. No percentages, ratios without units, arbitrary physical constants, logarithmic units, non-decimal numbers, year/date inference, or arbitrary user-defined conversion expressions are evaluated. Common temperature/time/pressure/energy/molar-concentration units and prefixed compounds are supported only to the closed extent in `references/unit-registry.md`.

No timestamp, host-specific absolute path, random ID, network state, benchmark score, or invented software status is included. The bundled example is synthetic and visibly labelled **SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE**.
