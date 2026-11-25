# Four-level verdict and evidence boundaries

These definitions are for Agent annotation of an original claim or probe **before** transition comparison. The expected relation is never a substitute for an evidence verdict.

## Verdicts

- `supported`: credible source evidence directly entails every material component of the claim at its stated population, condition, comparator, direction, polarity, statistical meaning, and causal or quantificational strength. Descriptive numerical ordering can support a descriptive comparison without establishing statistical significance.
- `partially_supported`: a material part is supported but another is weaker, narrower, indirect, incomplete, or unresolved. Examples include support for only one stated subgroup or support for association while a broader wording remains unsubstantiated. State exactly which components differ.
- `contradicted`: credible source evidence directly entails an incompatible proposition at the same material scope, such as the opposite observed direction, presence where absence is asserted, or a universal claim with observed counterexamples. This is not a synonym for lack of evidence.
- `insufficient_evidence`: accessible sources do not establish either the claim or its contradiction at the needed strength or scope; a required result is not reported; sources are inaccessible/unreadable; or evidence is too indirect to decide. Explain what would be needed when possible.

## Boundaries and traps

- **Topic related is not supported.** Shared treatment, organism, or endpoint terms merely motivate reading; the predicate and all operators still need evidence.
- **Not reported is not contradicted.** An unsupported causal extrapolation becomes `insufficient_evidence`, unless another adequate source directly rules it out.
- **Non-significance is not equivalence or no effect.** Preserve the reported estimate, uncertainty, test, and design. Conversely, a point-estimate direction is not statistical significance.
- **Correlation is not causation.** A causal probe may be `insufficient_evidence` even when its association original is `supported`. A randomized causal result does not automatically transfer to a different population or intervention.
- **Direction and lower-is-better outcomes matter.** Compare the actual numeric/event directions and units, not wording like “improved” alone.
- **Universal and existential claims differ.** One positive case may support `some`; a bounded exhaustive counterexample can contradict `all`. Do not generalize an existential result to a universal one.
- **Conditions bind the verdict.** Population, dose, time window, comparator, adjustment set, and outcome definition remain attached to the evidence. Broadening a scope commonly creates `insufficient_evidence`, not contradiction.
- **Compound claims are assessed as written.** Splitting is not the product of this Skill. If several material components are inseparable in the supplied question, `partially_supported` may be necessary, with the supported and unresolved portions named.

## Conflicts and uncertainty

Retain conflicting sources with separate `source_id`, locator, excerpt or faithful evidence summary, study design, and scope. Do not silently pick a preferred abstract or average conflicting conclusions. A conflict may warrant `partially_supported`, `contradicted` for the overbroad wording, or `insufficient_evidence`, depending on what each source entails; give the qualified reason in the annotation and final result. Explicitly distinguish missing materials, unreadable text, ambiguous wording, absent reporting, and genuine inter-source conflict.

Every evidence record should include `source_id`, a precise `locator`, a source-grounded snippet or faithful summary, and whether it supports or opposes the annotation. Independent adjudication means reading both statements on their own merits; it is not two-model agreement scoring.
