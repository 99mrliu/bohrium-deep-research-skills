# Quantity expression audit

Status: **partial**.
Case: SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE.

## Scope

Only typed quantity cells are changed. Identity is preserved; no deduplication, entity merging, scientific-conflict adjudication or missing-value imputation is attempted.
Case unit/number-region rules take precedence over material defaults. Unknown units and ambiguous numbers remain raw and enter review.

## Deterministic rule trace

- `QEC-PARSE-001`: stateful tokenization; recursive-descent quantity/unit parsing; conservative number-region handling.
- `QEC-UNIT-002`: exponent-vector dimensional check and explicit Decimal linear/affine conversion; interval reversal for a negative multiplier.
- `QEC-ROUND-003`: significant_figures, digits/places=6, ROUND_HALF_EVEN.

## Counts

- Rows: 11
- Ledger entries: 101
- Changed cells: 9
- Review items: 1

## Review codes

- `unknown_unit`: 1

## Sources

- `case.json` (case), SHA-256 `f4b0694859b0e3e48a032a29c04e3ec29cb94d09a45d6fd9a3f254fdda7cc966`
- `materials.json` (material), SHA-256 `d0ca5a93b54dc44b01e75dbc095010c45148c0604e5cbcc56d31493d7a36df7b`
- `measurements.csv` (material), SHA-256 `e3ac601b504bff009ffc4812d93843d572bf839d9e1c3ba75a07e78737f63ed2`
- `task.md` (task), SHA-256 `b523cf865d4b73d6b473e2987959d8838ec026a82e78d52668c1065e2d9a2ec4`

## Limits

The registry rejects unknown units. Missing data are not zero. Rounding controls presentation, not measurement confidence.
No automatic inference is made from task prose or field names alone; auto mode requires an embedded, registered unit.
