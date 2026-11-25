# Adjudication rules

## Demonstration, inference, absence, and conflict

1. **Demonstrated:** the source directly reports the specified direction for the specified subject/material, intervention, comparator, sample, conditions, and metric. Preserve all qualifiers. Statistical significance is not synonymous with importance, and a direct report is not independent proof of validity.
2. **Inferred:** the record connects reported findings to an interpretation or extrapolation. Supply anchored premises and `inference_reasoning`; label untested transfer explicitly. Never promote a plausible mechanism to a demonstrated effect.
3. **Not reported:** targeted methods/results/tables/discussion and relevant supplements were inspected or searched, but the dimension/claim is absent. Record `not_reported_basis`. This differs from an unreadable source and from no effect.
4. **Conflicting:** two or more anchored findings materially disagree for the same claimed scope. Retain both and use `conflict_note`. Different pre-specified strata may instead support separate bounded records with opposite directions.

## Counterexamples and universals

- A counterexample must share the universal's asserted domain or expose an undefined domain boundary. Link its record; do not rely on a vague disclaimer.
- One valid in-scope opposite result defeats `always`/`all`, even if the pooled effect favors the intervention.
- `bounded_restatement` rejects the universal and supplies a narrower claim. It does not make the universal conditionally true.
- `explained_out_of_scope` requires evidence that the exception lies outside the originally explicit domain. Narrowing the domain only after seeing an exception must be disclosed as a change record.
- `conflicting_evidence` leaves scope unresolved and normally makes the response partial if it affects a key requested answer.
- Null findings and missing evidence are not automatically counterexamples; they restrict certainty and coverage.
- `state of the art`, `best`, and equivalent rankings need a defined comparison set, search date, metric/unit, and comparable experimental conditions. A single-arm or single-dataset result cannot establish them.
- An abstract cannot close universal coverage. Methods, results, tables, and discussion each need an explicit checked entry and evidence anchor.
- Exception searches must include relevant synonyms, opposite-direction terms, subgroup/material/dataset names, and limitations. The number of searched terms is not proof of completeness.

## Status adjudication

- Use `success` only for complete requested bounded answers with traceable evidence. Rejecting an unsupported universal can still be a successful audit.
- Use `partial` when a material answer is under-scoped, required evidence is unreadable/missing, or conflict prevents closure.
- Use `failed` when no meaningful contract-valid answer is possible.
- Record every material narrowing, removed universal, reclassification, and late domain restriction in `change_records` or a sidecar.
- Put unresolved limitations in `uncertainty` or a sidecar. Do not use a successful JSON validation report to justify `success`.

## Checker limits

The scripts check required fields, explicit `NR`/`NA` reasons, unique IDs, evidence quote/anchor containment, declared section coverage, exception-search metadata, counterexample links, nonuniversal claim/record identity (including explicit composition exceptions), supported JSON contract constructs, and contract shape. They do **not** judge whether a quotation semantically supports a claim, whether a search was exhaustive, whether an exception is genuinely in scope, whether a documented composition is scientifically coherent, whether a comparator is fair, or whether an effect is causal. Those decisions remain documented human/model adjudication tasks. Bare `all` and Chinese `所有`/`全部` detection supplies adjudication prompts only.
