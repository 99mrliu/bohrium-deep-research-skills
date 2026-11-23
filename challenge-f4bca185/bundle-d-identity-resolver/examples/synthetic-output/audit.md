# Audit — identity resolver — case `synthetic-identity-001`

> **SYNTHETIC EXAMPLE RUN** — input is marked synthetic data for demonstration/self-check, not real literature.

- status: `success`
- lexicon: references/synonyms.json v1.0.0
- input records: 19
- output rows (clusters): 16
- rows merged as duplicates: 3
- candidate pairs: exact_duplicate=2, likely_duplicate=2, conflict=3, review=0, not_duplicate=8
- review queue items: 7; anomalies: 8
- rule-coded changes: 40

## Sources

- `source:10.0000/synth.a` (10.0000/synth.a): 13 record(s); locators: Table 1 row 1, Table 1 row 1, Table 1 row 2, Table 2 row 1, Table 2 row 2, Table 1 row 1, Table 1 row 1, Table 2 row 3, text p.4, Table 3 row 1, Table 3 row 2, Table 4 row 1, Table 4 row 1
- `source:10.0000/synth.b` (10.0000/synth.b): 4 record(s); locators: Table 1 row 1, Table 2 row 1, Table 3 row 1, Table 4 row 1
- `source:10.0000/synth.c` (10.0000/synth.c): 2 record(s); locators: Table 1 row 1, Table 1 row 2

## Invariants (self-check executed every run)

- [PASS] no_cross_source_merge: 0 violation(s)
- [PASS] no_cross_context_merge: 0 violation(s)
- [PASS] conflict_never_merged: 0 violation(s)
- [PASS] representative_is_member_row: 0 violation(s)
- [PASS] member_rows_retained: 0 violation(s)

## Rules applied (counts)

- A-001: 1
- D-001/D-002: 3
- D-008: 2
- D-009: 6
- F-002: 1
- N-003: 23
- N-004: 1
- N-005: 1
- N-006: 2
- U-002: 2
- U-003: 1
- U-004: 1
- V-002: 2
- V-003: 2

## Unresolved / human takeover points

- output_contract.custom_unmapped_note: no unambiguous semantic mapping from this field name to a computed artifact; left null rather than fabricated (result.json)
- missing_unit:r0008: value present but unit missing; normalized value stays null (review_queue.json)
- missing_value:r0009: missing value token 'not reported' normalized to null (review_queue.json)
- unknown_unit:r0015: unit 'Eg units' not in unit table; no conversion attempted, value compared raw only (review_queue.json)
- out_of_plausible_range:r0017: normalized value 25.0 eV outside plausible range [0.0, 15.0]; value kept unchanged, flagged for review (review_queue.json)

## Output contract coverage

- `cleaned_table` (dict): filled
- `custom_unmapped_note` (string): null (unresolved)
- `duplicate_clusters` (list): filled
- `review_summary` (list): filled
- `summary` (string): filled

## Traceability

- `change_log.json`: every automated change with rule id, before/after, input record id.
- `duplicate_report.json`: every candidate pair with evidence and decision rule; clusters keep all member rows and the representative selection rule D-008.
- `cleaned_records.json`: per-row `members[]` lineage back to original raw rows, sources and locators.
- Determinism: output contains no timestamps, absolute paths or randomness; identical input yields byte-identical output.
