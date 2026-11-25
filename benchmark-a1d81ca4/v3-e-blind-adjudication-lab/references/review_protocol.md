# Practical blind-review and adjudication protocol

## 1. Scope and roles

This protocol is for a fixed set of exactly four source-conditioned `benchmark-DRAFT` items. Deriving and exporting those four items is the primary task; the review protocol below is optional and applies only when actual reviewer artifacts exist. It does not build a source index, blueprint, generic scoring engine, or run ledger. The operational objects are:

1. **Source-conditioned item bank**: agent-derived questions, reference answers, 0/1/2 rubrics, and exact source locators from actual paragraphs/tables. Repository examples use synthetic sources only.
2. **Raw candidate output**: the answer that was actually submitted and will be reviewed, not an answer improved after seeing a score.
3. **Independent reviewer packet**: a per-assignment view without reviewer identity, candidate author, model/automatic score, or other reviewers' decisions.
4. **Human verdict**: an actually submitted independent decision, not a generated imitation.
5. **Adjudicator record**: a source-specific decision required for every pairwise disagreement, nonbinary observation, or incomplete review.
6. **Comparison/failure artifacts**: calibrated automatic-final label comparisons and actionable next-version probes.

Keep role separation practical: the person preparing packets must not reveal the key; reviewers must not share verdicts; the adjudicator sees the disputed verdicts and source evidence. Deterministic aliases are pseudonyms, not irreversible anonymization or an authorization system. Access restriction still matters.

## 2. Input JSON shapes

### Item bank

```json
{
  "case_id": "case-id",
  "items": [
    {
      "item_id": "DRAFT-001",
      "prompt": "Source-bounded question",
      "reference_answer": "Agent-derived from supplied evidence",
      "rubric": {"0": "incorrect", "1": "partial", "2": "correct"},
      "evidence_refs": [{"source_id": "S1", "locator": "table 1, row 2 and note"}]
    }
  ]
}
```

Exactly four items and four unique IDs are mandatory. An item may cite multiple excerpts. A rubric must explain all three levels rather than merely name them. Source references should identify table row/column/footnote or paragraph/sentence ranges, not only a document title.

### Candidate outputs and automatic scores

```json
{"outputs": [{"item_id": "DRAFT-001", "candidate_author": "private-author", "answer_text": "Actual submitted answer"}]}
```

```json
{"scores": [{"item_id": "DRAFT-001", "score": 2}], "scorer": "existing-scorer-label"}
```

The sets of IDs must equal the item-bank IDs; no missing, extra, or duplicate output/score is accepted. Scores are integers 0, 1, or 2. Automatic input is required by preparation so a complete pipeline cannot silently omit comparison data, but automatic metadata is never copied to packets. Candidate author is similarly dropped.

### Source evidence

```json
{
  "sources": [
    {
      "source_id": "S1",
      "title": "Actual source label",
      "source_type": "table",
      "synthetic": false,
      "excerpts": [{"locator": "table 1, rows 1-3 and note", "text": "Exact retained content"}]
    }
  ]
}
```

For actual work, preserve source provenance separately as required by the host task. For repository examples, every source has `synthetic:true`; this prevents fixture labels from becoming benchmark claims.

### Reviewer identities (private input)

```json
{"reviewers": [{"reviewer_id": "private-id", "display_name": "Private name"}]}
```

At least two unique reviewers are required. Assignment alias generation is deterministic over schema, assignment order, and reviewer ID. Reordering reviewers changes assignments, so freeze the ordered input before distributing packets. The private key maps alias to identity and relative packet file; it is outside `review_packets/`.

## 3. Packet and verdict protocol

A packet contains packet ID, assignment alias, rubric instructions, and four entries with:

- `item_id`, `prompt`, and `actual_answer`;
- `reference_answer`, `rubric`, and `evidence_refs`;
- `source_evidence`, where each entry carries source ID/title/type, synthetic marker, exact locator, and excerpt text.

Reviewers score independently without negotiating. One JSONL verdict per item:

```json
{
  "assignment_alias": "blind-...",
  "item_id": "DRAFT-001",
  "score": 1,
  "judgments": {"correctness": 1, "completeness": 1, "evidence": 2},
  "comments": "Which supported, omitted, or contradicted facts drive this score",
  "source_refs": [{"source_id": "S1", "locator": "table 1, rows 1-3 and note"}],
  "submitted_at": "2026-02-01T10:00:00Z"
}
```

Judgments must contain exactly `correctness`, `completeness`, and `evidence`, each integer 0/1/2:

- **correctness**: factual and inferential validity under the source;
- **completeness**: inclusion of all elements required by prompt/rubric;
- **evidence**: whether claims are supported and properly scoped by cited evidence.

The overall score need not be an arithmetic average; the item rubric controls. Use 1 only for genuinely partial content. Comments cannot be empty or a generic label. Source refs must exactly match the manifest. A timestamp needs a timezone. The deadline is inclusive; any later record is excluded as late.

### Data-quality handling

- Unknown item/alias: preserve in `unknown_id_records`, never remap by guessing.
- Malformed JSON, score, dimension, comment, ref, or timestamp: preserve an error and count the expected timely verdict as missing.
- Duplicate alias/item: exclude **all** duplicates rather than silently taking first/last; request a corrected independent submission. No reviewer may overwrite an existing verdict in place.
- Late record: retain in `late_verdicts`, exclude from accepted verdicts, and mark the expected verdict missing.
- Missing verdict: blocks strict **review** success (`review_status=partial`), not primary item-bank success. With three or more reviewers, pairwise disagreements are still computed only across timely accepted verdicts. If no actual verdicts exist at all, do not run adjudication: record `review_status=not_conducted_no_human_verdicts` and use typed not-applicable review artifacts.

The adjudicator must not infer that a unanimous result is true. Agreement only removes the adjudication trigger when every score/dimension is binary and the review is complete; source evidence remains the basis of item reference answers.

## 4. Adjudication schema and decision rules

```json
{
  "item_id": "DRAFT-003",
  "status": "resolved",
  "final_score": 1,
  "rationale": "Resolve the precise 0/1 boundary using supported and omitted source facts",
  "source_refs": [
    {
      "source_id": "S3",
      "locator": "paragraph 1, sentences 1-3",
      "evidence_note": "Sentence 2 supports the retained claim; sentence 3 supplies the omitted limit"
    }
  ],
  "unresolved_reason": null
}
```

For unresolved:

```json
{
  "item_id": "DRAFT-003",
  "status": "unresolved",
  "final_score": null,
  "rationale": "What was examined and why no source-grounded final label is defensible yet",
  "source_refs": [{"source_id": "S3", "locator": "paragraph 1, sentences 1-3", "evidence_note": "Decisive but insufficient passage"}],
  "unresolved_reason": "Specific additional evidence or rubric clarification needed"
}
```

An adjudication is triggered by any overall-score difference, any dimension difference, any 1 in overall score/dimensions, or missing expected verdicts. It may optionally be supplied for an undisputed binary item to document an automatic mismatch. A resolved adjudication can use 0, 1, or 2; final 1 is allowed only with rationale/evidence. Duplicate adjudication records, invalid refs, missing rationale, or missing evidence_note block resolution.

`pairwise_disagreements` stores each reviewer pair, score pair, differing dimensions, and judgment pairs. This is an audit trail, not a majority-vote algorithm. Reviewer agreement, majority votes, raw agreement, and kappa are never proof of truth.

## 5. Automatic-final comparison and small-sample limits

The comparison uses shared unweighted categories `0=incorrect`, `1=partial`, `2=correct`. No rescaling, imputation, averaging of unresolved verdicts, or substitution of an automatic score for a missing final is allowed.

For comparable resolved item set \(N\):

- `raw agreement = sum_i 1(auto_i == final_i) / |N|`;
- confusion matrix cell `(a,f) = count(auto_i=a and final_i=f)` for a,f in 0,1,2;
- `po = matches / |N|`;
- `pe = sum_c (automatic_count_c / |N|) * (final_count_c / |N|)`;
- `kappa = (po - pe) / (1 - pe)` only with at least four comparable items, at least two observed categories on each side, and nonzero `1-pe`.

The output prints exactly these numerators/denominators, including the count-product denominator `|N|^2` for pe. Unresolved/missing finals are listed separately and excluded from **all** agreement denominators. Exclusion makes a partial comparison diagnostic, not a complete success.

Four items cannot support stable prevalence, reliability, or model-ranking conclusions. Sparse/zero marginal cells, prevalence effects, and a single changed label can greatly change kappa. A computable value is labelled `SYNTHETIC LOW-N DESCRIPTIVE COMPARISON` (for this fixture), with no inferential, DSH-score, or truth claim. A final human adjudication is the operational comparison target, not an guarantee of infallibility; later source corrections require new change records.

## 6. Separate primary and optional-review finalization

The machine contract is read directly from `case.json`, never from task prose or a task JSON sidecar. Supported contract shapes are string lists, `fields` lists of strings or `{name:...}` objects, direct maps, `properties`, and `required_top_level_fields`.

Before primary `status=success`, verify:

- exactly four valid source-conditioned items have unique IDs, prompts, agent-derived reference answers, 0/1/2 rubrics, and valid evidence locators;
- all original contract fields are top-level, `case_id` is unchanged, and every field has an honest artifact binding (an unbound field makes primary status partial);
- sources, uncertainties, change records, summary, and diagnostics are present; scientific content is not invented or altered by finalization;
- primary completion is evaluated independently of optional review availability.

Without actual human verdict artifacts, a complete item bank remains `status=success`, with `review_status=not_conducted_no_human_verdicts`. Adjudication and agreement are typed `not_applicable` objects rather than null; no human kappa, agreement, failure, probe, or final score is claimed.

When review artifacts are supplied, preserve accepted human verdicts, pairwise disagreements, explicit adjudications, raw per-item comparisons, failures, and probes. Strict **review** success (`review_status=conducted`) additionally requires all four final scores, no nonempty review-quality/unresolved lists, and mismatch count equal to failure and probe counts. Incomplete/unresolved review stays `review_status=partial`; keep its final scores null and explain limitations, but do not downgrade an otherwise complete four-item primary result.

Never manufacture scientific answers, human verdicts, adjudications, comparisons, or calibration to make either status look complete.
