# Cleaning audit -- quantity ledger

- case_id: `None`
- status: **input_error**
- skill version: 1.0.0 (stdlib Python, Decimal-only arithmetic)
- case input: `examples/invalid/broken-case.json`
- task input: `examples/synthetic-task.md`

## Counts

- records: 0 (clean 0, review 0)
- conversions: 0; duplicate groups flagged: 0
- anomalies: 0; review items: 0; change records: 0

## Sources (sha256)

- `examples/invalid/broken-case.json` (json): 3f43b6296848744a07797018388d55f53839fe872188977ba35b09a621024124 -- 0 records

## Errors

- case JSON malformed: Expecting property name enclosed in double quotes: line 1 column 69 (char 68)

## Uncertainty / items requiring human confirmation

- none

## Method and precision notes

- Values are parsed with the grammar in `references/lexical-grammar.md`; ambiguous comma forms and malformed numbers are never guessed.
- Units use the rule table `references/units.json` (rule ids in every ledger row). Unknown or dimensionally incompatible units stay raw and go to review.
- Affine temperature rules (`U.degC`, `U.degF`) apply offsets to absolute values only; uncertainties are scaled by |multiplier| only and remain a separate field.
- Range midpoints and symmetric-uncertainty bounds appear only in `*_derived` columns; they are derived, not reported values.
- Duplicate detection only flags; nothing is merged automatically.
- Every change carries record id + input coordinates + rule id (see change_log.csv).

