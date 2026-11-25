# Independent metamorphic audit

- Case ID: `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`
- Delivery status: **partial**; verification: **pass**.
- Mode: verify-existing; all raw and candidate artifacts were reloaded from disk.
- Scientific scope: automated invariants detect process failures; they do **not** resolve scientific conflicts, source credibility, identity, or domain correctness.

## Checks

| Check | Result | Failures |
|---|---|---:|
| row_conservation_disposition_partition | pass | 0 |
| raw_value_immutability | pass | 0 |
| no_fabricated_missing | pass | 0 |
| unit_conversion_recomputation | pass | 0 |
| dedup_context_non_interference | pass | 0 |
| deterministic_rerun | pass | 0 |
| column_order_row_order_metamorphic_invariance | pass | 0 |
| whitespace_noise_metamorphism | pass | 0 |
| json_finite_value_completeness | pass | 0 |
| review_coverage | pass | 0 |
| source_locator_validity | pass | 0 |

## Minimal human audit sample

All blocking items are mandatory. Otherwise one deterministic representative per check is selected; this minimizes routine review without hiding risk.

| Review | Severity | Check | Source locator |
|---|---|---|---|
| RQ000001 | HIGH | dedup_context_non_interference | materials/literature.csv::row=2 |
| RQ000002 | MEDIUM | unit_conversion_recomputation | materials/literature.csv::row=1 |

## Unresolved and limitations

- Output-contract key `official_submission_reference` is null in result.json because no safe mapping is defined.
- Whitespace, row/column permutation, determinism, and exact-context dedup tests are process invariants, not proofs of bibliographic truth.
- Unit checks apply only to declarations in case/task; unknown units and conflicting sources require human/domain review.
- Missing-value tests prohibit unjustified fabrication but do not infer whether a source omission is scientifically meaningful.
- Counterexamples are executable debugging evidence, not a substitute for reviewing accepted rows.
