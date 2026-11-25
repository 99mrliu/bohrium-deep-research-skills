# Failure taxonomy, repair, and targeted retest guide

## Purpose

A failure case is created for each resolved item where the automatic 0/1/2 label differs from the adjudicated final label. It is a searchable example of automatic scoring behavior on that item, not evidence of population error rate or reviewer infallibility. Keep the original item ID in every probe's `retest_item_ids`; this is what makes a dispute useful in the next version.

Failure IDs have the form `FAIL-<item>-AUTO<a>-FINAL<f>`. Search keys include item ID, category, weakest human dimension, and `automatic-final-mismatch`. All examples in the repository are synthetic.

## Taxonomy

| Category | Recognition cue | Practical fix | Required targeted probe |
|---|---|---|---|
| `AUTO_OVERCREDIT_EVIDENCE` | Automatic score exceeds final; evidence is the weakest human dimension; answer makes unsupported inference, significance, causal, or scope claim | Require a source entailment check and an explicit unsupported-claim penalty; do not reward fluent citation alone | Retain original item; vary surface wording while preserving the unsupported inference and decisive source note; pass only when the final-calibrated score and evidence rationale both occur |
| `AUTO_OVERCREDIT_COMPLETENESS` | Automatic score exceeds final; completeness is weakest; prompt/rubric requirements were omitted | Build a rubric-element checklist, verify each required row/column/limit, and prevent partial answers reaching full credit | Use same omissions plus a paraphrased variant with identical missing elements; ensure no full credit until all required elements are present |
| `AUTO_OVERCREDIT_CORRECTNESS` | Automatic score exceeds final; correctness is weakest; numerical, directional, entity, or logical error was overlooked | Add deterministic value/unit/relation checks grounded in the quoted source; require contradiction detection before scoring | Preserve the numeric or logical trap, change irrelevant wording, and verify wrong relations cannot receive a high label |
| `AUTO_UNDERCREDIT_EVIDENCE` | Automatic score is below final; supported claims or valid source locators were not recognized | Normalize equivalent evidence expressions and recognize valid paraphrases without requiring exact reference wording | Test paraphrases of supported claims and equivalent source locator forms while keeping an unsupported contrast case |
| `AUTO_UNDERCREDIT_COMPLETENESS` | Automatic score is below final; the answer satisfied required elements but scorer missed them | Align rubric parsing with semantic coverage rather than token overlap; avoid double-counting omissions | Vary order and wording of all required elements; all-covered response should earn expected calibrated label |
| `AUTO_UNDERCREDIT_CORRECTNESS` | Automatic score is below final; correct values or relations were marked incorrect | Correct extraction/calculation and allow equivalent units, percentage-point language, or justified negation | Test equivalent units and valid alternative reasoning alongside a minimally changed incorrect control |

The implementation selects weakest dimension from accepted human dimension means. This is a deterministic triage heuristic for the failure label; the adjudicator's source-specific rationale remains the substantive diagnosis. If several dimensions tie, the script resolves the tie in fixed dimension order. A reviewer disagreement may reveal rubric ambiguity but does not replace source analysis.

## Additional non-mismatch workflow failures

These do not generate an automatic-final mismatch automatically, because there may be no resolved comparison. They block strict optional-review success or guide protocol repair, but do not block an otherwise complete four-item primary export:

| Operational category | Trigger | Repair and retest |
|---|---|---|
| `HUMAN_DISAGREEMENT_RUBRIC_BOUNDARY` | Reviewer scores/dimensions differ | Quote the contested rubric boundary, adjudicate with exact source facts, and add an item on the same boundary to reviewer training; do not resolve by averaging |
| `NONBINARY_WITHOUT_ADJUDICATION` | Any dimension or overall score is 1 without an explicit decision | Supply final 0/1/2, rationale, and evidence_note; retest the partial case and both neighboring binary cases |
| `SOURCE_LOCATOR_AMBIGUITY` | Ref cannot be uniquely matched or decisive text is outside excerpt | Restore exact paragraph/table locator and enough context; reject score finalization until reproducible |
| `REVIEW_RECORD_MISSING` | Timely valid expected verdict is absent | Obtain a new actual independent verdict; never synthesize one |
| `REVIEW_RECORD_DUPLICATE` | Same alias/item appears more than once | Exclude all copies and obtain a corrected submission preserving independence |
| `REVIEW_RECORD_LATE` | Submitted after the inclusive deadline | Exclude; collect under an explicitly new protocol run if continuation is allowed |
| `BLINDING_LEAK` | Identity, candidate author, scorer, or automatic score appears in packet | Remove leaked material, rotate packet distribution if reviewers saw it, and rerun independent review |
| `UNRESOLVED_FINAL` | Adjudicator cannot produce defensible source-grounded final | Keep final null and review partial; specify the evidence or rubric decision needed rather than imputing; keep primary item-bank status separate |

## Failure record interpretation

Each generated failure includes:

- `observed_behavior`: exact auto and final labels plus the weakest human dimension;
- `expected_behavior`: the next-version scoring behavior, not a demand to blindly copy humans;
- `human_dimension_means_descriptive`: low-N descriptive triage only;
- `evidence_refs` and `adjudication_rationale`: why the final comparison target was chosen;
- `fix.required_change`: an actionable scorer prompt/parser/check repair;
- `fix.not_a_fix`: editing final labels to agree, or treating agreement/kappa as truth;
- `search_keys` and stable `failure_id`.

Open failures are compatible with primary `success` and complete optional review: the four-item adjudication is complete and the mismatch has been converted into an actionable artifact. The underlying scorer issue remains explicitly `open` until the next-version retest passes. With no actual human verdicts, failures/probes are empty and not applicable, and the complete primary item bank can still succeed.

## Probe protocol

A generated targeted probe contains:

1. `reason`: the observed auto/final disagreement and failure category;
2. `retest_item_ids`: original fixed item(s), never a newly invented replacement alone;
3. `source_evidence_refs`: the decisive source locations;
4. `input_change`: keep the original regression and independently review one held-out, source-conditioned surface variant;
5. `expected_fix`: calibrated expected score and source-grounded rationale;
6. `pass_condition`: reproducible next-version score, correct decisive dimension and evidence, no unresolved substitution;
7. `expected_failure_if_unfixed`: the old score or an unsupported label;
8. `blinding_requirement`: do not reveal the old automatic score or adjudicator identity.

A useful next version tests:

- the original item unchanged;
- a paraphrased/control variant changing only non-decisive surface content;
- for scoring fixes, a nearby contrast item where the previously ignored limitation or correctness error flips the expected rubric label.

Do not use the old automatic score as probe input. Retain human disagreements and source refs for independent verification. If the new result differs from the old final, reopen source adjudication rather than changing the historical record silently; add a change record explaining source/rubric changes and rerun comparison.

## Search and small-sample cautions

Search failures by item ID, taxonomy category, weakest dimension, source ID, or retest ID. Start with repeated categories only after independent probes recur across genuinely different sources. Four items and two mismatches cannot establish a general model defect or fixed failure rate. Kappa and raw agreement can move sharply with one item and depend on category prevalence; neither validates a repair on its own. A repair passes only through source-grounded item-level behavior plus blinded retest evidence.
