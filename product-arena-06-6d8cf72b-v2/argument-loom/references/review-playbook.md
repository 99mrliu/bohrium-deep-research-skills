# Scientific argument review playbook

Use this checklist while reading actual paper pages. It supplies the human/agent semantic checks that deterministic validation intentionally does not perform.

## Preserve the section's work

- **Abstract:** identify the paper's compressed problem, approach, principal result, and bounded conclusion. Do not treat a promotional abstract sentence as stronger than Results.
- **Introduction:** separate established background, the gap, the research question/hypothesis, and claimed contribution. Prior-work citations are not automatically evidence for the paper's own result.
- **Methods:** capture design, sample/data, interventions, comparators, measurements, preprocessing, statistical tests, and assumptions. These often supply warrants rather than numerical evidence.
- **Results:** preserve estimands, direction, units, uncertainty intervals, sample size, controls, and figure/table provenance. Do not turn an association into causation or omit a null result.
- **Discussion:** distinguish interpretation from observation; map alternative explanations and applicability limits. Note where the authors soften or expand a result.
- **Conclusion:** check that recommendations remain within the population, setting, and evidence strength of the study.

Keep original section order even if the final narrative could be reorganized. A transition should explain the actual bridge (gap → question, method → observation, observation → interpretation), not merely state “next section.”

## Anchor-to-node semantic entailment

For each anchored node ask:

1. **Location:** Does the quote come from the stated section and paragraph, with no extracted-columns interleaving or OCR corruption?
2. **Proposition:** Does the source explicitly state the node, or is the node a visible reader inference? Paraphrase must preserve modality (“may,” “suggests”), negation, conditionality, and scope.
3. **Evidence fit:** Do the anchors support the same population, intervention/comparator, outcome, units, direction, and uncertainty as the claim? A nearby number is not necessarily supporting evidence.
4. **Warrant fit:** Does the warrant explain why this evidence licenses this claim (for example, controls reduce a specified alternative explanation)? Repeating the result is not a warrant.
5. **Limit fit:** Does the limitation actually bound this claim? Generic cautions must not be attached without a source-grounded connection.
6. **Transition fit:** Does the bridge reflect author reasoning and preserve order rather than inventing a narrative?
7. **Cross-section consistency:** If Abstract, Results, and Discussion differ, record the difference rather than silently harmonizing it.

Mark `reviewer_confirmed` only after these checks. Mark `disputed` and record the issue in uncertainties when anchors are topically related but do not entail the node. The script checks the status vocabulary, not the correctness of this judgment.

## Honest reading and QA

Report missing input, unreadable content, and readable-but-unreported content separately. For partial OCR, quote only recovered text and identify the affected pages/sections. For competing interpretations, retain both with their own anchors. Do not manufacture warrants or limitations to achieve structural completeness; use `not_reported` where appropriate.

For direct QA, translation, or extraction, respond to the requested item first and cite the smallest sufficient anchor. Optional graph material belongs only in notes tasks. In translation, preserve qualifiers and numerical detail; in extraction, distinguish exact text from normalized representation; in QA, say `not_reported` when the readable paper lacks the answer.

## Final review

Trace every core claim along `evidence → claim`, `warrant → claim`, and any `limitation → claim`. Read the graph section by section against the paper, then inspect outgoing transitions. Confirm that uncertainty language and status records survive into Markdown and `result.json`. Deterministic PASS is a floor for traceability; the reviewer remains responsible for scientific interpretation.
