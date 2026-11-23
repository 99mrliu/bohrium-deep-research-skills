# Cleaning audit -- quantity ledger

- case_id: `synthetic-quantity-001`
- status: **partial**
- skill version: 1.0.0 (stdlib Python, Decimal-only arithmetic)
- case input: `examples/synthetic-case.json`
- task input: `examples/synthetic-task.md`

## Counts

- records: 18 (clean 11, review 7)
- conversions: 13; duplicate groups flagged: 1
- anomalies: 5; review items: 6; change records: 53

## Sources (sha256)

- `examples/synthetic-case.json` (json): d84c05db95a42813405381c32ccb4930bf85b88b12ca7ac3c0af376db1e1dd6d -- 15 records
- `examples/synthetic-extra.csv` (csv): 3d313bdbfc20e1bf995e1c2d535c3ef07bdb2b7c30c0bede2ed9e2c700db0871 -- 3 records

## Errors

- none

## Uncertainty / items requiring human confirmation

- `RV0001` [malformed_number] record s07 @ `examples/synthetic-case.json#$.records[6]`: cannot parse numeric token '12.3.4'
- `RV0002` [unknown_unit] record s08 @ `examples/synthetic-case.json#$.records[7]`: unknown unit symbol 'quatloo'
- `RV0003` [missing_value] record s09 @ `examples/synthetic-case.json#$.records[8]`: no value supplied; left empty, never imputed
- `RV0004` [ambiguous_decimal_comma] record s12 @ `examples/synthetic-case.json#$.records[11]`: '1,234': single comma followed by exactly three digits
- `RV0005` [missing_value] record R0017 @ `examples/synthetic-extra.csv#row3`: no value supplied; left empty, never imputed
- `RV0006` [duplicate_group] record s02 @ `examples/synthetic-case.json#$.records[1]`: 2 records share the conservative duplicate key: examples/synthetic-case.json#$.records[1], examples/synthetic-case.json#$.records[9]

## Method and precision notes

- Values are parsed with the grammar in `references/lexical-grammar.md`; ambiguous comma forms and malformed numbers are never guessed.
- Units use the rule table `references/units.json` (rule ids in every ledger row). Unknown or dimensionally incompatible units stay raw and go to review.
- Affine temperature rules (`U.degC`, `U.degF`) apply offsets to absolute values only; uncertainties are scaled by |multiplier| only and remain a separate field.
- Range midpoints and symmetric-uncertainty bounds appear only in `*_derived` columns; they are derived, not reported values.
- Duplicate detection only flags; nothing is merged automatically.
- Every change carries record id + input coordinates + rule id (see change_log.csv).

