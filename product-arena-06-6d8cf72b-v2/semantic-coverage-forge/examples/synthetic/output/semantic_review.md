# SYNTHETIC semantic review

**Entirely fictional example; not real research evidence.**

Structural gate: **PASS**. Machine semantic status: **NOT_AUTO_VERIFIED**.

This authored checklist is not independent truth certification. Exact quote retrieval, schema validity, and required-term presence do not prove whole-answer entailment or completeness.

## Review protocol

1. `explicit_question_and_contract_decomposition`
1. `direct_answer_before_citation`
1. `adversarial_omission_comparator_negation_condition_generalization_review`
1. `whole_answer_evidence_entailment_human_check`
1. `two_sided_conflict_and_derivation_check`
1. `absence_status_and_checked_scope_check`
1. `structural_schema_as_final_gate`

## Item reviews

### Q1 — answered

**Question:** At 12 weeks, what mean orientation score did the authors report, and was that number author-reported or calculated from the excerpt?

**Direct answer:** The authors reported a 12-week mean orientation score of 82.4 points; the value was author-reported, not calculated from the excerpt (n=36).

**Evidence role/count:** `author_reported` / 1

**Checked scope:** Checked S1 (Twelve-week results) in full for the time point, mean orientation score, units, sample size, and reported-versus-derived provenance.

- **omission:** Both requested components are present: the 12-week orientation mean (82.4 points) and its author-reported rather than calculated provenance.
- **comparator:** Q1 requests one reported mean, not a group contrast; no between-group direction or baseline was invented.
- **negation:** The phrase 'not calculated from the excerpt' preserves the provenance limit while leaving the reported value intact.
- **condition:** The 12-week endpoint, orientation-score endpoint, points unit, and n=36 denominator all match S1.
- **unsupported generalization:** The answer reports a study mean only; it makes no efficacy, participant-wide, or beyond-excerpt claim.
- **whole answer entailment:** The single S1 quotation contains the mean, time point, unit, sample size, and author-reported wording used by the answer; human entailment review remains required.
- **conflicts two sided:** No competing orientation mean appears in S1, S2, or T1, so there is no Q1 value conflict to reconcile.
- **formula derived vs author reported:** The 82.4-point value is labelled author-reported; SEM 1.2 was not used to derive a new estimate.
- **status integrity:** Q1 is answered with one S1 evidence item whose anchor is inside its declared checked scope.
- **Residual uncertainty:** No additional uncertainty is inferred beyond the excerpt's reported mean and SEM.

### Q2 — answered

**Question:** In Table 1 at the Reed site, how did Compass A's mean completion time compare with Compass B's, including the exploratory/unadjusted conditions and units, and can the comparison be generalized to other sites?

**Direct answer:** At the Reed site only, Compass A's mean completion time was 1.3 minutes lower than Compass B's (8.1 vs 9.4 minutes), a difference calculated from the two reported means; the comparison was exploratory and unadjusted (n=12 per group). No, this table does not support generalizing the comparison to other sites.

**Evidence role/count:** `mixed` / 1

**Checked scope:** Checked T1 (Table 1, Reed-site exploratory completion times) in full for both means, units, comparator direction, sample size, conditions, and other-site scope.

- **omission:** The response supplies both Reed means, their direction and difference, minutes, per-group n, exploratory/unadjusted conditions, and an explicit answer about other-site generalization.
- **comparator:** Compass A (8.1 minutes) is correctly described as 1.3 minutes lower than Compass B (9.4 minutes), using B as the stated baseline.
- **negation:** The explicit 'No' blocks the requested other-site generalization instead of implying it from a favourable numerical difference.
- **condition:** Every comparison clause remains tied to Reed site only and to the exploratory, unadjusted T1 analysis with n=12 per group.
- **unsupported generalization:** The response does not infer superiority at other sites or statistical significance from an unadjusted descriptive comparison.
- **whole answer entailment:** T1 supports both input means and all restrictions; the matrix separately documents the calculated subtraction rather than pretending T1 reports 1.3 minutes.
- **conflicts two sided:** T1 contains one Reed comparison and no other-site completion results, so the answer does not suppress a competing site estimate.
- **formula derived vs author reported:** Formula: 9.4 minutes - 8.1 minutes = 1.3 minutes; Compass A minus Compass B = -1.3 minutes, so A is 1.3 minutes lower. Inputs: Compass A: author-reported 8.1 minutes at Reed; Compass B: author-reported 9.4 minutes at Reed Rounding: One decimal place, matching both reported inputs; the difference is calculated, not author-reported.
- **status integrity:** Q2 is answered with mixed evidence: T1 supplies the reported means while the matrix records the derived direction and difference.
- **Residual uncertainty:** The difference is exploratory, unadjusted, and restricted to Reed; no other-site or significance conclusion is supported.

### Q3 — not_reported

**Question:** What 95% confidence interval is reported for the 12-week mean orientation score?

**Direct answer:** Not reported in the checked excerpt: S1 gives the mean and SEM, but no reported 95% confidence interval or CI bounds for the 12-week mean orientation score; no CI was calculated.

**Evidence role/count:** `no_evidence_expected` / 0

**Checked scope:** Checked S1 (Twelve-week results), S2 (Statistical reporting), and T1 (Table 1) in full for a reported 95% confidence interval or lower/upper CI bounds. None appears. The SEM 1.2 in S1 is not treated as a CI; this not_reported status is limited to the supplied excerpt.

- **omission:** The response states that no 95% CI or CI bounds are reported for the 12-week mean and separately notes that no CI was calculated.
- **comparator:** Q3 requests interval bounds rather than an arm comparison; no lower/upper pair or arm contrast was fabricated.
- **negation:** 'Not reported in the checked excerpt' is explicitly bounded and does not become a claim that no study anywhere reports this interval.
- **condition:** The absence statement remains restricted to the 12-week orientation score and the enumerated S1, S2, and T1 excerpt anchors.
- **unsupported generalization:** The answer neither converts SEM 1.2 into a confidence level nor invents a symmetric interval around 82.4 points.
- **whole answer entailment:** S1 provides the near-miss SEM while S2 explicitly excludes CI bounds and calculations; these are reviewed as scope evidence, not inserted as fake support quotes.
- **conflicts two sided:** The excerpt contains no competing CI bounds; the only potential confusion is SEM versus CI, which the answer resolves without substitution.
- **formula derived vs author reported:** No CI formula was applied and no interval is represented as author-reported; the task prohibits deriving one from SEM here.
- **status integrity:** Q3 uses not_reported, retains evidence=[], and documents all three checked anchors rather than manufacturing an absence quotation.
- **Residual uncertainty:** Not reported only in S1, S2, and T1 of the supplied excerpt; this is not a claim about other documents.

## Honest not-reported handling

Q3 has `evidence: []`. Its checked scope enumerates S1, S2, and T1. SEM is not converted to a CI, and no evidence item was fabricated to make the row look supported.

## Change records

- **Q2:** The authored answer includes Reed-only, exploratory, unadjusted, n=12 per group, comparator direction, units, calculated provenance, and refusal to generalize. **Reason:** Condition, comparator, derivation, and unsupported-generalization review.
- **Q3:** The authored answer distinguishes SEM from a 95% CI, leaves evidence empty, and lists S1, S2, and T1 as checked scope. **Reason:** Not-reported integrity; no fabricated evidence or derived CI.

## Paths

- `result`: `result.json`
- `answer_matrix`: `answer_matrix.json`
- `audit_report`: `audit_report.json`
- `semantic_review_json`: `semantic_review.json`
- `semantic_review_markdown`: `semantic_review.md`
