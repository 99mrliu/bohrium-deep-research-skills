# Actual inspection record — synthetic example

All observations below come from executing this delivered version locally with Python 3. All data are **SYNTHETIC**. No official cases, hidden targets, benchmark scores, or formal-test outputs were used.

## 1. Contract and integration tests

Command, run from the skill directory:

```bash
mkdir -p .tmp
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.tmp" \
  python3 -m unittest discover -s tests -v
```

Observed result:

```text
test_every_named_mutation_is_rejected_and_base_is_untouched ... ok
test_scaffold_and_finalizer_failure_never_clobber_valid_output ... ok
Ran 2 tests ... OK
```

Inspection of the second test's assertions confirmed all of the following: the scaffold emitted two pending `extraction_failed` records with null scalar values and top-level `partial`; the valid draft finalized successfully; a subsequent `unit_altered` draft exited 1 with `UNIT_NOT_IN_QUOTE`; and the SHA-256 of the previously finalized valid output was identical before and after that rejection.

## 2. End-to-end synthetic example

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 examples/minimal/run_example.py
```

Observed per-copy subprocess results (not invented expectations or scores):

| Mutation | Actual validator exit | Expected code actually observed | Control result |
|---|---:|---|---|
| `wrong_subject` | 1 | `SUBJECT_MISMATCH` | pass |
| `wrong_condition` | 1 | `CONDITION_MISMATCH` | pass |
| `wrong_comparator` | 1 | `COMPARATOR_MISMATCH` | pass |
| `scalar_absent_from_quote` | 1 | `SCALAR_ABSENT_FROM_QUOTE` | pass |
| `unit_altered` | 1 | `UNIT_NOT_IN_QUOTE` | pass |
| `statistic_dropped` | 1 | `STATISTIC_DROPPED` | pass |
| `false_not_reported` | 1 | `VALUE_ON_NOT_REPORTED` | pass |
| `unsupported_source_conflict` | 1 | `SOURCE_CONFLICT_REQUIRES_TWO_SOURCES` | pass |
| `duplicate_field` | 1 | `DUPLICATE_FIELD_ID` | pass |
| `missing_field` | 1 | `MISSING_FIELD_ID` | pass |
| `quotation_paragraph_mismatch` | 1 | `QUOTE_NOT_IN_PARAGRAPH` | pass |
| `hedged_claim_promoted` | 1 | `HEDGED_CLAIM_PROMOTED` | pass |
| `stale_condition_alias` | 1 | `CONDITION_ALIAS_MISMATCH` | pass |
| `stale_mirrored_fields` | 1 | `FIELD_RESULTS_NOT_MIRRORED` | pass |

The terminal output also showed:

```text
valid base: actual_pass=true
finalizer: actual_pass=true exit=0 byte_identical=true
valid base unchanged after every mutation: true
Passing structural and mutation tests proves only these explicit validator behaviors on the synthetic fixture. It does not prove semantic correctness of this or any real extraction. An agent must perform decoy review against the original material.
```

The generated `audit-report.json` reports 14 mutations run, 14 expected-rejection controls passed, zero failed, and no base validation errors. The generated `cli-rejections.json` records the actual exit status and observed codes for every separate validator process. `benchmark_score` is null and `official_case` is false.

## 3. Manual output inspection

I inspected the generated files after execution:

- `generated/valid-result.json` has `case_id` `SYNTHETIC-ADVERSARIAL-GATE-V1`, top-level status `answered`, two uniquely requested field records, literal `12.4`, `nM`, and `mean ± SD` in the p1 quote, an honest null-valued `not_reported` second field, and a `speculation` claim retaining *suggest/may*.
- `generated/audit-report.json` has base SHA-256 before/after `418c556ae5ed960dbc7d34007f330a543a4726379821c5a6a42b1bb1bdafd0a4` and `unchanged: true`. Every mutation has `actual_validator_rejected: true`, `expected_code_observed: true`, and `base_unchanged: true`.
- `generated/cli-rejections.json` has base hashes identical before/after all 14 nonzero validator invocations, `finalizer_actual_exit_status: 0`, `finalizer_reproduced_valid_bytes: true`, and `overall_actual_pass: true`.
- `generated/finalized/result.json` is byte-identical to `generated/valid-result.json` as checked by the example, not merely visually similar.
- `generated/finalized/finalization-report.json` explicitly has `semantic_correctness_proven: false`.

These runs demonstrate the named validator rejection behaviors and byte-level mutation isolation. They do not establish semantic correctness for any actual paper. Real cases still require decoy review against original material, including source layout and full-scope absence checks.
