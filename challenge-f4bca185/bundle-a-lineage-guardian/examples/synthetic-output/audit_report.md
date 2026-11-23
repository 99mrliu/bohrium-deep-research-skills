# SYNTHETIC Lineage Guardian Audit — NOT AN OFFICIAL ANSWER

- case_id: `SYNTH-LINEAGE-001`
- status: **success**
- schema_version: `1.0.0`

## Run policy

Raw input is immutable in the raw snapshot. Unknown units stay unconverted; missing values stay null; duplicate candidates are flagged without merging. Original papers were not independently re-read.

## Input integrity and provenance

| source | path | SHA256 | BOM | decode status | replacement chars | raw rows |
|---|---|---|---:|---|---:|---:|
| S001 | `case.json` | `ff3c09aa5d95f84982b18ec1cf8e44f1bceebbf7f4f8ff2d611355a75f801975` | false | valid_utf8 | 0 | 2 |
| S002 | `dirty_records.csv` | `8495db18e05c3f6fc196a0c81cf2ecadee55d64e9d06fd013a40575d2fb08082` | true | valid_utf8 | 1 | 9 |

## Counts

- source_count: **2**
- table_count: **2**
- raw_row_count: **11**
- cleaned_row_count: **10**
- excluded_empty_rows: **1**
- change_record_count: **143**
- anomaly_count: **13**
- review_item_count: **13**
- duplicate_group_count: **2**
- unknown_unit_count: **2**
- missing_value_count: **1**

## Rule application counts

| rule | count |
|---|---:|
| R-ANM-006 | 1 |
| R-DUP-002 | 4 |
| R-DUP-003 | 3 |
| R-FLD-002 | 88 |
| R-FLD-006 | 1 |
| R-NAM-001 | 7 |
| R-UNIT-002 | 20 |
| R-UNIT-007 | 2 |
| R-UNIT-008 | 16 |
| R-VAL-005 | 1 |

## Review hotspots

- `Q00001` **R-ANM-002** `None`: U+FFFD is present in decoded input; it may be original corruption or decode recovery.
- `Q00002` **R-ANM-005** `T002-R00003`: Unit is not in the explicit conversion dictionary; value remains unconverted.
- `Q00003` **R-ANM-005** `T002-R00005`: Unit is not in the explicit conversion dictionary; value remains unconverted.
- `Q00004` **R-ANM-003** `T002-R00006`: Property value is absent or explicitly missing; null is retained.
- `Q00005` **R-ANM-002** `T002-R00007`: Affected cell contains U+FFFD; verify it against the original extraction.
- `Q00006` **R-ANM-006** `T002-R00009`: An entirely empty/missing-token row was excluded from cleaned rows but retained in raw_snapshot.json.
- `Q00007` **R-DUP-002** `T001-R00001`: Duplicate extraction candidate within one context; no automatic merge occurred.
- `Q00008` **R-DUP-002** `T001-R00002`: Duplicate extraction candidate within one context; no automatic merge occurred.
- `Q00009` **R-DUP-003** `T002-R00001`: Rows share material/property/value but differ in experiment context; merging is forbidden without adjudication.
- `Q00010` **R-DUP-003** `T002-R00002`: Rows share material/property/value but differ in experiment context; merging is forbidden without adjudication.
- `Q00011` **R-DUP-003** `T002-R00008`: Rows share material/property/value but differ in experiment context; merging is forbidden without adjudication.
- `Q00012` **R-DUP-002** `T002-R00001`: Duplicate extraction candidate within one context; no automatic merge occurred.
- `Q00013` **R-DUP-002** `T002-R00002`: Duplicate extraction candidate within one context; no automatic merge occurred.

## Output artifacts

| artifact | file | SHA256 |
|---|---|---|
| cleaned_csv | `cleaned_rows.csv` | `e95ef1f8937b14828abd93b8c71f55ee13eefd829476b71d78c97a0722e6a019` |
| cleaned_rows_json | `cleaned_rows.json` | `75997ad8eda1e3903a9cc5b3c2cefc0d30f19efd88ff7d5a4ee7e1c7e6f42b4b` |
| raw_snapshot | `raw_snapshot.json` | `495fc5c44c5c3554820687a1b8195b8235126e9393fd4dcefab67e8b5d95b7af` |
| change_log | `change_log.jsonl` | `48e39820476768aa6d74f4a57ccc6eae100bf50fb381d6f92801f8303b05c2a4` |
| review_queue | `review_queue.json` | `ed69c0774deba3a73537b6d7517ffa5e5c2f1d1d7345d2942fc869aaa67725fd` |

## Unresolved output-contract fields

- `custom_extension` = null (no safe semantic mapping; not fabricated)

## Reproduction and limits

Run with Python 3.10+ standard library only. No clock, random seed, network, locale-dependent sort, or external package affects output. Audit paths describe this run's inputs; artifacts use relative filenames. Ranging preserves endpoints, not midpoints. A successful status means processing completed, not that review items are scientifically resolved.
