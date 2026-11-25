# SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE

# Rule-spec compilation audit

- case_id: `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`
- status: `partial`
- plan_sha256: `c37d8ec6fdc2fb5146c7fcef923bed9da365550b60978bbae6a220c3c93ade94`
- input_rows: 4
- output_rows: 4
- changed_cells: 19

## Compiled rules

- `R-rename-field-ddc7ebbcd1e1` — rename_field, priority 100, executed; provenance `[{"pointer":"/field_mappings/Dose Text","source":"case.json"}]`
- `R-normalize-missing-0bc3d0a69cdc` — normalize_missing, priority 200, executed; provenance `[{"pointer":"#L7","source":"task.md"}]`
- `R-trim-whitespace-aac2617e6f7a` — trim_whitespace, priority 300, executed; provenance `[{"pointer":"/rules/0","source":"case.json"}]`
- `R-literal-map-484e6936edfe` — literal_map, priority 350, executed; provenance `[{"pointer":"/rules/0","source":"rules.json"}]`
- `R-parse-number-5208a9ff2c3a` — parse_number, priority 400, executed; provenance `[{"pointer":"#L8/0","source":"task.md"}]`
- `R-parse-number-ab0709dfd899` — parse_number, priority 400, held; provenance `[{"pointer":"#L13/rules/0","source":"task.md"}]`
- `R-parse-number-fd9a32485e88` — parse_number, priority 400, held; provenance `[{"pointer":"/rules/0","source":"conflict-override.json"}]`
- `R-normalize-range-8455021ee517` — normalize_range, priority 420, executed; provenance `[{"pointer":"/range_fields","source":"case.json"}]`
- `R-convert-unit-5140a9787f33` — convert_unit, priority 440, executed; provenance `[{"pointer":"/unit_targets/dose_g","source":"case.json"}]`
- `R-validate-identity-ad3252076e93` — validate_identity, priority 900, executed; provenance `[{"pointer":"#L9","source":"task.md"}]`

## Review

- `Q-23705b588e8f47bc` **RULE_CONFLICT**: incompatible rules target yield; all are held

## Contract

Unresolved required fields: none

Missing values remain empty. No imputation, silent conflict resolution, row deduplication, random order, network access, or clock-derived value is used.
