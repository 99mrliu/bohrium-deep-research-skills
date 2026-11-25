# Independent probe and mutation design

## Purpose

A probe tests the **decision boundary**, not whether JSON or `machine_check` is nonempty. Every probe stores raw candidate text, an independently assigned 0/1/2 score, the expected pass/fail value of every predicate, and a short reason. Write these labels from the source and intended rubric before executing the suite. Never derive or refresh expected labels from scorer output.

`mutation_check.py` loads exactly four items and each item's embedded `probes`. IDs are globally unique. It fails on missing/duplicate IDs, unknown classes, incomplete expected-predicate maps, score disagreement, predicate disagreement, and missing required classes.

## Required classes per item

| `probe_class` | Minimal question answered | Typical expected score |
|---|---|---|
| `exact` | Does the source-backed reference answer receive full credit? | 2 |
| `paraphrase` | Does a meaning-preserving alternative with required units/conditions receive full credit? | 2 |
| `partial` | Is an answer with a deliberately missing essential component distinguished from full credit? | 1 |
| `wrong_entity` | Can an otherwise fluent answer naming the wrong row/compound/cohort be exposed? | 0 or justified 1 |
| `wrong_numeric` | Is a wrong numeric magnitude not accepted as the target value? | usually 0/1 |
| `wrong_value` | Is a wrong qualitative value/status/relation exposed? | usually 0/1 |
| `wrong_unit` | Does the same numeral with a wrong required unit fail the numeric predicate? | usually 0/1 |
| `omitted_condition` | Is a necessary context such as dose, duration, population, container, or follow-up window distinguished? | usually 1 |
| `negation_reversal` | Is “not/without/failed” distinguished from the positive assertion? | usually 0 |
| `empty` | Does `""` safely and deterministically receive zero? | 0 |
| `unsupported` | Is fluent material not supported by the item prevented from earning credit merely by being nonempty? | 0 |

Add `legitimate_unreported` when the source truly does not report the requested value. Such an answer can deserve **2**, not zero, if the item explicitly rewards saying unreported and rejects substitution of another time point. Other probe classes remain required for that item, including wrong numeric/unit probes.

A wrong answer may receive justified partial credit when other independent components are correct. The point is to test the declared rubric, not to force every error to zero. Record why in each probe and score band. If two checks overlap so heavily that no probe can distinguish them, redesign the checks.

## Concrete synthetic pattern

Suppose the synthetic source says: “For S-17, NQ-7 at 120 °C for 3 h gave an isolated yield of 82.4%.” A useful suite includes:

- exact: “S-17 使用 NQ-7，在 120 °C 反应，分离产率 82.4%。” → all core checks true, score 2.
- paraphrase: “NQ‑7 was used at 120°C; isolated yield = 82.4 percent.” → normalized alternatives/numeric units true, score 2 only if the rubric declares those alternatives.
- partial: “NQ-7，分离产率 82.4%。” → temperature check false, score 1.
- wrong unit: “NQ-7，120 °C，分离产率 82.4 mg。” → yield numeric check false even though the numeral is right, score per band.
- negation: “S-17 未使用 NQ-7，120 °C，82.4%。” → forbidden/reversal check false.
- unsupported: “收率完美，显然优于所有催化剂。” → no unsupported fluency credit.

These strings are illustrations of synthetic probe design, not answers to any real case.

## Mutation strategy

Run the positive suite first, then deliberately alter a **copy** in the output/work directory. A meaningful negative mutation is one that creates an observable wrong acceptance or deletes test coverage. Examples:

1. Add `mg` to the yield rule's accepted `%` units. The existing `wrong_unit` probe should change from its expected behavior, and mutation check must fail. Do not update the expected label to accept mg.
2. Remove one `wrong_numeric` probe. The suite must fail with missing required class even if every remaining score agrees.
3. Remove a forbidden child for “未使用 NQ-7”. The negation-reversal expected predicate should disagree.
4. Reverse two score bands or omit a condition from the 2 band. Exact/omitted-condition probes should expose the boundary change.

A changed expected label is not a mutation of the scorer; changing raw candidate text together with its expectation can conceal a bug. Keep the probe suite fixed while mutating a rubric, or keep the rubric fixed while deleting/duplicating a probe. Save the executable rejection report. The bundled runner inspects its negative report to confirm the intended wrong-unit probe actually became accepted at score 2; any zero exit from the mutated run fails the example.

## Determinism and independence checks

- Execute engine, mutation, raw-output scoring, and finalization twice in separate output directories.
- Compare reports byte-for-byte. Reports deliberately contain no wall-clock timestamps or random IDs.
- Confirm candidate raw-output SHA-256 and rubric hashes match across runs.
- Confirm the four scores sum to the reported total and that the denominator is exactly 8 for four required items.
- Confirm refusal behavior separately for unknown/missing/duplicate IDs, empty output, and overlimit output where changing these policies matters.
- Review disagreements manually; do not turn the scorer into an oracle by auto-labeling.

## Known limits

A fixed suite cannot enumerate the space of paraphrases or contradictions. Passing all probes does not prove semantic correctness, source completeness, human agreement, or rubric monotonicity outside tested points. Numeric, negation, and cross-entity cases in other languages need additional authored probes. An incorrect independent expectation can also cause a disagreement; resolve it by source/rubric review and an explicit rationale, never by blind acceptance of actual output. Escalate ambiguous evidence, legitimate answers outside declared alternatives, and suspicious all-green mutations for manual review.
