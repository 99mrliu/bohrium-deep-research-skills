# Probe planning, independent annotation, and review protocol

## Workflow

1. Parse the supplied claims without treating them as facts. Accept a top-level list or a dictionary containing `claims`, `claims_to_verify`, or `items`. Preserve supplied claim IDs and compound wording.
2. Independently adjudicate each original using the complete context. Save annotations before creating probe comparisons to reduce anchoring.
3. Generate a small candidate plan across high-risk operators. Include all six signature keys for the base and probe. Use an exact `edit_contract` whose `find` occurs exactly once in the base text and whose replacement produces exactly the probe text.
4. Assign priority **before** probe verdicts are available. Operator risk weights are causality 100, negation 95, comparison 90, significance 88, quantifier 85, and condition scope 80. `risk_boost` and source-grounded `risk_flags` may increase priority; verdicts, expected transitions, and annotation outcomes are excluded from sorting. The selector stratifies by operator, then fills remaining slots by risk, with deterministic seed-based tie breaking. Default maximum is 12, hard maximum 24. Excluded candidates remain listed in selection metadata.
5. Independently adjudicate every selected probe. Record its own evidence and full semantic signature. Never fill it by applying the expected relation to the original verdict.
6. Run `transition_check.py`. It refuses missing/multiple semantic edits and plan/annotation signature mismatches with exit `1`; it reports expectation/observation mismatches with exit `2`; success is exit `0`.
7. For exit `2`, re-open the paper. Inspect design, estimates, direction, denominator, qualifiers, surrounding limitations, and conflicting sources. Record the review before changing anything. Create an updated annotation file rather than erasing the initial file. A result cannot claim success with unresolved re-review items.

## Candidate plan shape

```json
{
  "schema_version": 1,
  "synthetic": false,
  "probes": [
    {
      "probe_id": "p-causal",
      "base_claim_id": "c1",
      "probe_text": "Exposure X caused outcome Y in the stated cohort.",
      "operator": "causal_correlation",
      "risk_boost": 20,
      "risk_flags": ["observational_design"],
      "base_signature": {
        "negation": "affirmative",
        "comparison_direction": "not_applicable",
        "significance": "not_applicable",
        "causal_correlation": "correlational",
        "quantifier": "not_applicable",
        "condition_scope": "stated_cohort"
      },
      "probe_signature": {
        "negation": "affirmative",
        "comparison_direction": "not_applicable",
        "significance": "not_applicable",
        "causal_correlation": "causal",
        "quantifier": "not_applicable",
        "condition_scope": "stated_cohort"
      },
      "edit_contract": {"find": "was associated with", "replace": "caused"},
      "semantic_relation": "strengthen",
      "expected_relation": "become_insufficient"
    }
  ]
}
```

The `find` text above is illustrative and must match the actual base statement in a real plan. `semantic_relation` and `expected_relation` have distinct meanings defined in `verdict_operations.md`.

## Annotation shape

```json
{
  "schema_version": 1,
  "synthetic": false,
  "annotations": [
    {
      "id": "c1",
      "text": "Exposure X was associated with outcome Y in the stated cohort.",
      "verdict": "supported",
      "semantic_signature": {"negation": "affirmative", "comparison_direction": "not_applicable", "significance": "not_applicable", "causal_correlation": "correlational", "quantifier": "not_applicable", "condition_scope": "stated_cohort"},
      "evidence": [{"source_id": "paper", "locator": "Results, paragraph 2", "snippet": "Source-grounded evidence text", "stance": "supports"}],
      "rationale": "Independent source reading rationale.",
      "uncertainty": ["Any residual limitation."],
      "conflicts": []
    }
  ]
}
```

Use one annotation object per original and selected probe, with unique IDs and exact matching text. `verdict` must be one of the four defined levels. `snippet` must be source-grounded; a concise faithful excerpt is preferred, but transition correctness does not depend on quotation matching. Every conflict object should name both source IDs and locators. Sources are listed in a UTF-8 `sources.json` such as:

```json
{"sources": [{"source_id": "paper", "path": "paper.txt", "title": "Actual source title", "synthetic": false}]}
```

Relative source paths are resolved relative to `sources.json`. At runtime, point to copies or supplied materials under `/app/work` and retain their original page/field locators. Binary runtime papers are allowed; the Skill bundle itself is text-only.

## Required review record

For every inconsistency or repaired illegal probe, append a structured change record containing `record_id`, `stage`, `target_id`, `before`, `after`, `source_locators`, `rationale`, and `review_status` (`resolved` or `unresolved`). Preserve initial and revised annotation filenames in `before`/`after` or adjacent metadata. Never delete the failed transition report. A corrected verdict must cite the evidence that motivated it; “the checker expected this” is not sufficient rationale.

## Early and partial delivery

The contract skeleton is the first output. Save annotations, selected plans, and reports as they become available. If time or source access runs out, copy the latest valid partial result to `/app/output/result.json`, list unread claims/sources and pending re-reviews in `uncertainty`, and keep completed evidence records rather than fabricating the rest.
