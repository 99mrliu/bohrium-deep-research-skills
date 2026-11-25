---
name: adversarial-extraction-gate
description: Validate literature conclusion/data extraction with source-bound records, isolated adversarial mutation controls, and agent decoy review. Use for structured scientific field extraction, evidence verification, conflicting/not-reported values, or final QA of result.json.
---

# Adversarial extraction gate

Build one evidence-bound record per requested field, then challenge plausible misreadings before delivery. The tools check the result contract and exact quotations against an agent-built source corpus. They use only Python's standard library.

**Passing structural validation or mutation tests does not prove semantic correctness.** Mutation controls demonstrate only that specified corruptions of a synthetic fixture are rejected. A literal quotation can still support the wrong subject, condition, comparator, time point, or claim. The reading agent must perform the decoy review in `references/decoy-review.md`; a self-generated assertion of correctness is not that review.

## Run this workflow on every case

1. Read `/input/case.json`, `/input/target-fields.json`, `/input/task.md`, and every actual supplied material. Use the original `case_id`; read concrete target IDs and request bindings rather than inferring them from filenames. Inspect the environment's advertised parsing/OCR tools when the material is a PDF.
2. Immediately create an honest partial, before lengthy reading. From this skill directory run:

   ```bash
   python3 scripts/scaffold.py
   ```

   This creates `/app/output/result.json`, `/app/work/draft-result.json`, an input inventory, an empty corpus template, and a needs-revision decoy-review template. Every requested field begins as `extraction_failed` with null values and a *pending* note; this does **not** mean the source failed to report it. Existing output is not overwritten. A nonzero scaffold status means an input problem remains documented in the early result.
3. Read and extract incrementally into `/app/work/draft-result.json`. Build `/app/work/source-corpus.json` from exact source text using `references/field-contract.md`. Keep paragraph IDs stable and copy quotes verbatim. Do not normalize units, calculate implied values, promote a hedge, or substitute a nearby better-documented measurement. Update `change_records` with material revisions; record unreadable regions and searches in `uncertainties`.
4. Run the standalone gate while revising:

   ```bash
   python3 scripts/validate_result.py \
     --result /app/work/draft-result.json \
     --targets /input/target-fields.json \
     --case /input/case.json \
     --corpus /app/work/source-corpus.json
   ```

   Status 0 means structurally accepted; 1 means rejected extraction; 2 means malformed inputs/resources. Treat every reported error as a correction lead, not permission to bypass the gate.
5. Perform a source-facing adversarial pass. For each field, actively compare the best-supported reading with same-number/wrong-entity, wrong-condition, wrong-comparator, wrong-time, absence, conflict, and hedging decoys that are plausible in this paper. Record concrete observations in `/app/work/decoy-review.json` using `references/decoy-review.md`. Review all fields and claims, including `not_reported`; do not merely rerun the validator.
6. Finalize only after correcting draft and review:

   ```bash
   python3 scripts/finalize.py
   ```

   The finalizer reruns the contract checks, requires complete decoy-review records, and runs the isolated synthetic mutation audit in memory. It writes `/app/output/result.json` only when all gates pass, plus the audit and finalization reports. On rejection it leaves an existing delivered result byte-identical and keeps the rejected draft in work. The report always sets `semantic_correctness_proven` to false.
7. Ensure the final JSON covers every requested `field_id` exactly once in `result.fields` and, if present, identically in `result.field_results`. Return the required JSON deliverable, not just an audit summary.

## Required result shape

Top-level keys are `case_id`, `status`, `result`, `claims`, and `uncertainties`; `sources` and `change_records` are optional arrays. Top-level status is one of:

- `answered`: every requested field has a definitive extraction disposition, including a justified `not_reported` or documented `source_conflict`.
- `partial`: some requested material, field, or verification remains incomplete.
- `insufficient_evidence`: the available material cannot support the requested answer.
- `input_error`: required inputs are absent or malformed.

Each field record contains exactly the required contract information (additional annotation is allowed):

```json
{
  "field_id": "requested-id",
  "status": "reported|not_reported|source_conflict|extraction_failed",
  "subject": "subject bound by the target/source",
  "scalar": "literal scalar or null",
  "units": "literal units or null",
  "statistic": "literal statistic or null",
  "experimental_condition": "condition or null",
  "condition": "exact alias",
  "comparator": "comparator or null",
  "paragraph_id": "source paragraph or null",
  "quote": "verbatim quote or null",
  "evidence": {"source_id": "id", "page": 1, "paragraph_id": "p1", "quote": "verbatim quote"},
  "notes": "scope, uncertainty, or search/failure note"
}
```

For `reported`, scalar/units/statistic must remain literal in the quote. For `not_reported` and `extraction_failed`, scalar, units, and statistic stay null and notes distinguish exhaustive absence from incomplete/failed extraction. For `source_conflict`, those values also stay null, `quote` and `paragraph_id` are null, `evidence` is a list of at least two distinct source locations with nonidentical verbatim quotes, and notes explain the disagreement without selecting an unsupported winner.

Each key claim needs `claim_id`, `kind`, `statement`, `source_id`, `location`, and `evidence`. Keep `speculation`, `limitation`, and `explicit_conclusion` distinct. Preserve modal language such as *may*, *might*, and *suggests*. Use `uncertainties` for true absence, conflict, unreadable material, extraction limits, and manual-review needs; never convert uncertainty into zero or certainty.

See `references/field-contract.md` for the corpus and validator rules, `references/mutation-catalog.md` for negative controls, and `examples/minimal/README.md` for the explicitly synthetic executable example. This bundle contains no official case answers, benchmark scores, hidden targets, third-party dependencies, or prepared formal-test outputs.
