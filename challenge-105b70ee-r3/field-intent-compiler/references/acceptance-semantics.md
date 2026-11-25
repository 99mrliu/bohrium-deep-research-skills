# Acceptance semantics and review playbook

This guide contains **SYNTHETIC illustrations only**. Its rules are field-agnostic and do not encode official-case answers.

## Why literal evidence is insufficient

A candidate can be an exact quote and still answer the wrong question. Common failures include:

- the requested mean replaced by an individual observation, SD, SE, median, or confidence limit;
- the requested treatment arm replaced by a control arm mentioning the same metric;
- a value at the wrong dose, temperature, solvent, time point, population, or preprocessing protocol;
- an absolute value substituted for a difference, ratio, fold change, or effect versus a named baseline;
- a main-text statement used when the target schema limits scope to a supplement, or vice versa;
- a speculative sentence rewritten as an established conclusion;
- a same number located in the right paragraph but bound to another row header or merged-table condition.

The acceptance contract forces those distinctions to be settled from the target question/schema first. The evidence quote is checked afterward against the contract, not used to define the contract.

## Applying each axis

1. **Metric identity**: write the measured quantity and any transformation precisely. “Yield”, “conversion”, and “selectivity” remain different even when co-located. “Change in yield” differs from final yield.
2. **Subject/entity**: identify material, arm, cohort, sample, replicate level, and time point where requested. Do not let a nearby subject inherit a value.
3. **Expected value form**: distinguish single scalar, range, interval, list, categorical label, and verbatim text. Preserve ranges and error notation rather than silently reducing them to a point.
4. **Requested unit**: retain the source unit when no conversion is requested. A numeric scalar plus separate unit does not license dropping the original `verbatim_value`. Derived conversions must be explicitly requested and separately explained; this compiler does not perform them.
5. **Statistic**: distinguish raw observation, n, mean, median, SD, SE, variance, CI bound, p value, and significance label. A replicate count does not imply any variability statistic.
6. **Required condition**: all conditions must bind jointly to the candidate. A matching number under another condition is a rejected candidate, not supporting evidence for the answer.
7. **Comparator**: identify baseline, direction, contrast, and whether absolute or relative. `none` is meaningful only when the question requests no comparison.
8. **Source scope**: enforce permitted documents/sections and search all in-scope material before absence. If a scope is ambiguous, resolve it from the schema or acknowledge ambiguity rather than choosing the convenient source.
9. **Modality**: for conclusions, preserve the author stance. Established observations, author interpretations, recommendations, limitations, and speculation are not interchangeable. Keep qualifiers such as “may”, “suggests”, “under these conditions”, and “within this dataset”.
10. **Verbatim evidence**: exact source/location/quote is a mechanical integrity gate. It cannot compensate for failure on axes 1–9.

## Decision discipline

- Evaluate decoys explicitly. Record instructive rejected candidates with the failed test ID, especially same-number wrong-condition matches.
- Do not confuse task difficulty with source absence. Use `extraction_failed` for unreadable cells, missing permissions, broken text, or unresolved table structure.
- Do not turn imperfect retrieval into `not_reported`. Declare absence only after a recorded, sufficiently broad in-scope search.
- Keep conflicts unresolved unless the actual task provides an adjudication rule. Preserve each candidate and its exact evidence; never average or prefer the first value.
- Report an honest partial result. One well-supported field is compatible with several unresolved fields and overall `partial` status.
- Keep source registration separate from adjudication. The register supplies locations/text; the agent supplies semantics; the compiler supplies structural gates. None of these layers should fabricate another layer's work.

## Audit review

A reviewer should be able to start with `contract-audit.md`, read the pre-candidate interpretation, see every semantic pass rationale and rejected near-match, and follow the exact evidence tuple back to the source. The contract hash binds decisions to the interpreted schema. The source-register hash in change records binds the final result to the registered text.

Those hashes establish artifact consistency, not scientific truth. A reviewer must still open the original materials and confirm paragraphs, table headers, conditions, and modality. In particular, a malicious or mistaken agent can falsely mark a semantic check as passed; no stdlib compiler can independently prove natural-language semantics without making the very keyword-based assumptions this skill avoids.
