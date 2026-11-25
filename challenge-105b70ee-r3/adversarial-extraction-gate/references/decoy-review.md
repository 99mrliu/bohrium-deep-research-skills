# Agent decoy review: the semantic gate

A validator can reject contradictions in the submitted representation, but a convincing wrong answer can be internally consistent. The reading agent must therefore try to **falsify** each extraction against the original material. This is a substantive reading step, not a checkbox and not a second invocation of the same validator.

## Procedure

1. **Reconstruct the question before the answer.** For each requested field, write a short mental query containing subject, measure, condition/time, comparator, and required statistic. Then locate candidate source passages before looking at the chosen value again.
2. **Generate local adversarial alternatives.** Search the same paragraph, adjacent rows/captions, other treatment groups, and supplement for plausible decoys. Choose decoys because they occur in this material; do not invent generic counterexamples unrelated to the paper.
3. **Compare binding, not superficial similarity.** A good quote binds subject, condition, comparator, statistic, scalar, and units to the requested field. If the binding comes from a heading or neighboring sentence, preserve enough exact contiguous/source-linked context and inspect that layout in the original/rendered page.
4. **Attempt to overturn the current disposition.** Prefer the alternative if the source genuinely supports it. Revise field, claim, notes, and uncertainty together; regenerate `field_results` from `fields`. Never edit evidence merely to make a desired value pass.
5. **Record what was actually observed.** Name concrete checked decoy classes and the source locations that discriminated them. `reviewer` should identify the executing agent/person. A record with no observation is rejected by the finalizer.

## Minimum decoy matrix

| Failure to challenge | Source-facing question |
|---|---|
| Wrong subject | Does another group, analyte, species, intervention, or outcome use the same wording/value? Does the quote actually bind the requested subject? |
| Wrong condition or time | Is this a different dose, temperature, time point, sample, assay, subset, or baseline? Is a number being moved out of its qualifying phrase? |
| Wrong comparator | Is the comparison versus baseline, control, another active arm, or a cross-study value? Did a reference column shift? |
| Scalar absent from quote / same-number decoy | Is the exact scalar in this quote, and does it label the requested measure rather than a sample size, concentration, or other endpoint? |
| Unit altered | Is the unit printed with this value? Do prefixes, `%`, concentration denominators, or per-time components survive verbatim? |
| Statistic dropped | Are mean/median, SD/SE/IQR, CI, range, sample size, P value, or significance qualifiers attached to this exact value? |
| False `not_reported` | Could the field occur in a table, figure caption, supplement, abbreviation, or explicit textual form? Was all requested material searched? Never use nearby data as a substitute. |
| Unsupported `source_conflict` | Do two exact source locations genuinely disagree about the same subject/condition/metric? Could different conditions or units explain the apparent conflict? Do not resolve a real conflict by preference. |
| Quotation/paragraph mismatch | Is this quote verbatim in the cited location, with the correct page, row, column, or caption? Does a similarly worded paragraph elsewhere contain it instead? |
| Hedged claim promoted | Do *may/might/could/suggest/appear*, limitation language, or equivalents remain in the statement and kind? Is association being promoted to causation? |
| Absence versus failure | `not_reported` needs adequate source coverage; OCR failure, missing material, pending reading, or ambiguous extraction is not source absence. |

For every field status, including `not_reported`, perform the applicable rows. For claims, inspect surrounding limitation/discussion text in addition to the chosen quotation.

## Review file

Save `/app/work/decoy-review.json`:

```json
{
  "schema": "decoy-review/v1",
  "case_id": "actual-case-id",
  "semantic_correctness_not_proven": true,
  "reviewer": "reading-agent",
  "field_reviews": [
    {
      "field_id": "actual-field-id",
      "verdict": "pass",
      "decoys_checked": ["wrong_condition", "same_number_elsewhere"],
      "observation": "Concrete source locations and observations that distinguish the chosen reading."
    }
  ],
  "claim_reviews": [
    {
      "claim_id": "actual-claim-id",
      "verdict": "pass",
      "decoys_checked": ["hedge_promotion"],
      "observation": "What the original claim and adjacent limitations actually say."
    }
  ]
}
```

There must be exactly one field review per target and one claim review per claim. The finalizer requires each verdict to be `pass`, at least one recorded decoy class, and a nonempty observation. If a material uncertainty remains, use `needs_revision` in the work record, revise the result/status, and repeat review before finalization; do not force a pass merely to satisfy the tool.

Even a complete review is fallible. The audit and finalization reports therefore always state that semantic correctness is not proven. Independent human/source review remains appropriate for high-stakes use, parser uncertainty, layout ambiguity, and true source conflicts.
