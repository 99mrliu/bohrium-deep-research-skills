# Field contract and evidence corpus

## 1. Request bindings

`target-fields.json` may be an array or an object containing `fields`, `target_fields`, or `targets`. It must contain a nonempty list with unique nonempty `field_id` strings. Optional request bindings used by the validator are:

| Target key | Field key checked | Why |
|---|---|---|
| `subject` | `subject` | Prevents moving a correctly quoted value to another subject. |
| `experimental_condition` (or `condition`) | both condition aliases | Prevents detaching a value from its requested setting. |
| `comparator` | `comparator` | Prevents baseline substitution. |
| `statistic_required: true` | `statistic` | Prevents silently dropping an explicitly requested statistic. |

These are request constraints, not permission to infer scientific values from a target. No expected numeric answer is built into this bundle. If a real target does not declare these bindings, the agent still preserves them from the source and must use decoy review to check semantic attachment.

## 2. Source corpus

The validator resolves quotes against `/app/work/source-corpus.json`, which the reading agent constructs during the run from the actual supplied material. It is a verification aid, never a source of guessed text or an expected answer layer.

```json
{
  "schema": "evidence-corpus/v1",
  "sources": [
    {
      "source_id": "paper-main",
      "title": "Actual source title",
      "paragraphs": [
        {"page": 4, "paragraph_id": "results-p2", "text": "Exact extracted paragraph text."}
      ]
    }
  ]
}
```

Rules:

1. Assign stable source identifiers to the main paper, supplement, table extraction, or figure caption as appropriate. IDs must agree with `result.sources` and evidence.
2. Preserve the original wording and Unicode in `text`. If a supplied parser produced the text, retain its actual page and stable paragraph/table/caption identifier in your notes. Do not silently repair source wording inside a quote.
3. `page` may be an integer or a source-specific page label. `paragraph_id` plus `source_id` must be unique in the corpus. Every corpus paragraph needs `page`, `paragraph_id`, and string `text`.
4. A field/claim quote must be an exact substring of the named paragraph—not a normalized match, concatenation, paraphrase, or substring found only elsewhere.
5. A table cell may be represented as a stable paragraph record such as `table2-row3-cell4`, but notes must make its row/column location independently checkable. For composite context, include the exact contiguous extracted text that binds headers and cell; never invent punctuation or headers.
6. When no usable text layer exists, record the OCR/render inspection limit. Do not fabricate paragraph text. Use partial or failed status until evidence is genuinely available.

The corpus can establish exact quotation/location consistency only. It cannot prove that corpus text is complete or faithfully parsed; source-facing decoy review must inspect the original or its rendered pages.

## 3. Field semantics

All field objects require `field_id`, `status`, `subject`, `scalar`, `units`, `statistic`, `experimental_condition`, `condition`, `comparator`, `paragraph_id`, `quote`, `evidence`, and `notes`.

- **`reported`**: one evidence object is required. Top-level quote and paragraph exactly mirror primary evidence. The scalar must literally occur in the quote; numeric strings are not converted or rounded. Nonempty units and statistic must also be literal substrings. Null units are suitable only for a genuinely unitless/textual result; explain this in notes when useful. `condition` exactly mirrors `experimental_condition`.
- **`not_reported`**: scalar, units, and statistic are null. Evidence is optional and top-level quote/locator are null if no evidence is supplied. Notes identify the searched source scope and field. Use only after the requested material was inspected sufficiently to distinguish absence from extraction failure. A related metric is not the requested metric.
- **`source_conflict`**: scalar, units, statistic, top-level quote, and top-level paragraph are null. `evidence` is an array containing at least two distinct source/paragraph locators with nonidentical quotes. Notes explain the actual disagreement. Multiple mentions of the same value or a vague concern about methods are not conflicts.
- **`extraction_failed`**: scalar, units, and statistic are null. Notes state what remains unreadable, unavailable, ambiguous, or pending. This is appropriate for the early scaffold and incomplete extraction, not a shortcut for a well-searched absence.

`result.field_results` is optional; when included, it must be an exact JSON mirror of `result.fields`. Update both by regenerating the mirror from the canonical fields, never by independent editing. Requested field IDs must appear exactly once, with no extra IDs.

## 4. Claims and uncertainty

Each claim has a unique `claim_id`, a `kind`, a nonempty `statement`, top-level `source_id`/`location`, and one source-resolved `evidence` object. Suggested kinds include `reported_finding`, `explicit_conclusion`, `speculation`, and `limitation`. Hedged evidence cannot support an `explicit_conclusion`, `causal_conclusion`, or `established_fact` when the statement removes all hedges.

Retain numerical qualifiers, error/statistic terms, conditions, comparators, and limitations in claims. Uncertainties should identify field/claim IDs where possible and distinguish `not_reported`, `source_conflict`, `extraction_failed`, parser/OCR limits, and manual review. Top-level `partial` is honest when material remains unexamined; `answered` does not require that every field has a reported value.

## 5. Validator behavior and exit status

`validate_result.py` emits JSON with `actual_pass`, the checked path, structured errors, and `semantic_limit`. It rejects duplicate JSON object keys and non-finite numbers as input errors. Main rejection codes include:

| Code | Detection |
|---|---|
| `DUPLICATE_FIELD_ID`, `MISSING_FIELD_ID`, `UNREQUESTED_FIELD_ID` | Request-to-result cardinality mismatch. |
| `SUBJECT_MISMATCH`, `CONDITION_MISMATCH`, `COMPARATOR_MISMATCH` | Explicit target binding changed. |
| `CONDITION_ALIAS_MISMATCH`, `FIELD_RESULTS_NOT_MIRRORED` | Internal duplicate representation diverged. |
| `SCALAR_ABSENT_FROM_QUOTE`, `UNIT_NOT_IN_QUOTE`, `STATISTIC_NOT_IN_QUOTE` | Literal value component is absent. |
| `STATISTIC_DROPPED` | Target-required statistic is missing. |
| `VALUE_ON_NOT_REPORTED`, `VALUE_ON_SOURCE_CONFLICT`, `VALUE_ON_EXTRACTION_FAILED` | A nonreported disposition still carries a value. |
| `SOURCE_CONFLICT_REQUIRES_TWO_SOURCES`, `SOURCE_CONFLICT_NOT_INDEPENDENT` | Conflict lacks distinct evidence. |
| `QUOTE_NOT_IN_PARAGRAPH`, `UNKNOWN_EVIDENCE_LOCATOR`, `EVIDENCE_PAGE_MISMATCH` | Evidence cannot be resolved exactly. |
| `FIELD_EVIDENCE_PARAGRAPH_MISMATCH`, `FIELD_EVIDENCE_QUOTE_MISMATCH` | Duplicated primary citation diverged. |
| `HEDGED_CLAIM_PROMOTED` | A hedge detector finds promotion in specified claim kinds. |

CLI status is 0 for no detected contract violation, 1 for a rejected candidate, and 2 for malformed/unavailable inputs or corpus. Status 0 is not a correctness score. The quote and hedge detectors are deliberately conservative and can miss paraphrased linguistic changes; numeric equality by conversion is intentionally not accepted because the challenge requires literal preservation.
