# Minimal semantic operators and expected transitions

## One-operator construction

A valid probe changes exactly one of the following semantic operators while preserving every other material aspect of the original claim. The plan contains an exact one-span `find`/`replace` edit, complete before/after signatures, and the original/probe texts. The checker requires exactly one changed signature key and requires independently supplied annotation signatures to match. The exact edit prevents disconnected multi-point edits; signatures also reject a single large replacement that hides multiple operators. Neither mechanism derives a verdict from strings.

The six signature keys and boundaries are:

| Operator | Typical single edit | Semantic signatures must preserve |
|---|---|---|
| `negation` | `did not reduce` ↔ `reduced` | Comparator, outcome direction, significance, causal mode, quantifier, conditions |
| `comparison_direction` | `larger than` ↔ `smaller than`, or one explicitly paired comparator inversion | Polarity, statistical meaning, population, outcome and units |
| `significance` | `not statistically significant` ↔ `statistically significant` | Point-estimate direction and effect size; never infer one from the other |
| `causal_correlation` | `was associated with` → `caused` | Association direction, covariates, population, endpoint and comparator |
| `quantifier` | `some` → `all`, or `all` → `some` | Predicate, denominator/domain, conditions and comparison |
| `condition_scope` | `adults with mild symptoms` → `adults regardless of symptom severity` | Intervention, outcome, time window and all non-target conditions |

Signature values are short semantic labels such as `negative`, `affirmative`, `A_over_placebo`, `significant`, `correlational`, `existential`, or `mild_adults`. All six keys are required; use `not_applicable` when an operator is absent. For example, statistical `not_significant` is represented only under `significance`, not also as predicate negation. This convention avoids counting one statistical edit twice.

Do not use probes that change treatment, endpoint, unit, dose, time window, or study population in addition to the declared operator. Rephrasing without a semantic operator change is not a counterfactual probe. Negating an entire universally quantified statement often changes quantifier scope as well as polarity; use an explicit predicate negation or reject the probe. Opposite causal directions and opposite correlation directions are comparison changes, not merely causal-mode changes.

## Two relation fields

Keep logical claim strength separate from the expected evidential transition:

- `semantic_relation` describes the probe proposition relative to the original: `same` (equal strength, including direction polarity flips), `weaken` (logically less demanding), or `strengthen` (logically more demanding). It does not predict a verdict by itself.
- `expected_relation` is an evidence-aware calibration expectation the Agent records **before reading the independent probe verdict**. The checker compares it with the actual independent annotations.

Expected relation transition consistency:

| `expected_relation` | Accepted observed `original -> probe` transition |
|---|---|
| `same` | The two verdicts are identical. |
| `weaken` | `supported -> partially_supported`, `supported -> insufficient_evidence`, or `partially_supported -> insufficient_evidence`. This describes weaker evidential support, not a weaker proposition. |
| `strengthen` | `insufficient_evidence -> partially_supported`, `insufficient_evidence -> supported`, or `partially_supported -> supported`. |
| `flip_to_contradicted` | Any non-`contradicted` original verdict to `contradicted`. The original source must genuinely oppose the probe, not merely omit it. |
| `become_insufficient` | Any non-`insufficient_evidence` original verdict to `insufficient_evidence`. The probe lacks adequate evidence; it is not thereby disproved. |

`semantic_relation=strengthen` can legitimately accompany `expected_relation=become_insufficient` (association to causation, some to all without exhaustive data, or narrow to broad scope). It can also accompany `flip_to_contradicted` when the records contain direct counterexamples. A semantically equivalent direction inversion normally has `expected_relation=flip_to_contradicted` only when the source actually establishes the opposite direction.

These relations are checks on calibration, not algebra for producing truth. A mismatch means re-read both statements, evidence locators, the semantic parse, and the expectation. Record any correction and its justification in `change_records`; unresolved mismatches remain visible and force an honest partial final status.
