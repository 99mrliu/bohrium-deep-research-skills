# Isolated adversarial mutation audit

## What the audit proves

The audit starts with one explicitly synthetic, source-resolvable result. It verifies that result without mutation, then builds each negative control with `copy.deepcopy`. Every mutation calls the same `validate_result` function used for candidate extraction. A test passes only when:

1. the unmutated synthetic base is accepted;
2. the mutant is rejected with the **named expected error code** (an unrelated rejection does not count);
3. the base object's canonical bytes are unchanged before and after that mutation; and
4. the final base and delivered `valid-result.json` hashes remain unchanged.

All candidate corruptions happen in isolated in-memory copies. When `--output-dir` is supplied, invalid copies are separately serialized under `corrupted/` only after validation; the valid base is never used as the mutation target. The finalizer calls the same audit with no output directory and never applies a mutation to the real case draft.

This is executable negative-control evidence, not a benchmark score and not evidence about official cases. Passing all controls does not prove semantic correctness, parser fidelity, full source coverage, or the truth of an agent's decoy review.

## Catalog

| Mutation name | Realistic corruption | Required rejection code |
|---|---|---|
| `wrong_subject` | Assign the value to SynB instead of requested SynA. | `SUBJECT_MISMATCH` |
| `wrong_condition` | Change both condition aliases to condition X. | `CONDITION_MISMATCH` |
| `wrong_comparator` | Substitute comparator X. | `COMPARATOR_MISMATCH` |
| `scalar_absent_from_quote` | Replace 12.4 with plausible but unsupported 99.9. | `SCALAR_ABSENT_FROM_QUOTE` |
| `unit_altered` | Change nM to mg/mL. | `UNIT_NOT_IN_QUOTE` |
| `statistic_dropped` | Remove required mean ± SD. | `STATISTIC_DROPPED` |
| `false_not_reported` | Relabel a populated reported field as absent. | `VALUE_ON_NOT_REPORTED` |
| `unsupported_source_conflict` | Declare conflict while retaining one source and a value. | `SOURCE_CONFLICT_REQUIRES_TWO_SOURCES` |
| `duplicate_field` | Duplicate one requested record in fields and its mirror. | `DUPLICATE_FIELD_ID` |
| `missing_field` | Drop one requested field from fields and its mirror. | `MISSING_FIELD_ID` |
| `quotation_paragraph_mismatch` | Use a real sentence from p2 while still citing p1. | `QUOTE_NOT_IN_PARAGRAPH` |
| `hedged_claim_promoted` | Replace suggest/may speculation with an unhedged explicit conclusion. | `HEDGED_CLAIM_PROMOTED` |
| `stale_condition_alias` | Leave `condition` inconsistent after condition revision. | `CONDITION_ALIAS_MISMATCH` |
| `stale_mirrored_fields` | Change a scalar in only `field_results`. | `FIELD_RESULTS_NOT_MIRRORED` |

The first 12 are the core user-facing failure suite; the last two guard duplicated representations against silent stale edits. The report retains all actual errors, so extra detected violations are visible rather than hidden.

## Run it independently

From the skill directory:

```bash
python3 scripts/mutation_audit.py --output-dir /app/work/mutation-audit
```

The command exits 0 only if every actual control expectation above passes; otherwise it exits 1. The report includes `overall_actual_pass`, per-mutation `actual_validator_rejected`, `expected_code_observed`, `base_unchanged`, and `pass`. `benchmark_score` is explicitly null. No official result is read by this command.

The minimal example additionally invokes the CLI once per serialized corrupted copy, records its real process exit status, and requires a nonzero exit plus the expected code. See `examples/minimal/run_example.py` and `examples/minimal/INSPECTION.md`.

## Boundaries

These are directed unit controls, not proof of completeness against every adversarial phrasing. In particular, target metadata may not contain all semantic bindings, hedges may be paraphrased in languages not covered by the detector, and exact quote matching cannot establish quote selection. Agent decoy review is mandatory precisely because an internally consistent mutant outside these patterns can still validate.
