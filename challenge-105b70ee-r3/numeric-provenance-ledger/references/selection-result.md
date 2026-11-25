# Semantic selection and result contract

## Selection is the Agent's reasoning boundary

Scripts lex and verify; they do **not** decide which quantity answers a target. After reading `task.md`, every target definition, source text, and the ledger inventory, the Agent writes `selection.json` with exact ledger IDs. No embedding, string-similarity score, numeric proximity score, first-match rule, largest/smallest-value preference, or model-free “reported answer” selector is used.

```json
{
  "schema_version": "numeric-selection/v1",
  "fields": {
    "requested-field-id": {
      "status": "reported",
      "value_token_ids": ["N000005"],
      "condition_token_ids": ["N000004"],
      "statistic_token_ids": ["N000007"],
      "reference_token_ids": ["N000009"],
      "notes": "Why this quantity, condition, cohort, and comparator match the target"
    }
  }
}
```

`fields` must contain exactly the IDs in `target-fields.json`, neither omitting difficult fields nor inventing extra requested answers. The selection file may contain additional prose metadata; the semantic decision is represented by IDs and status.

### Reported

A `reported` selection has exactly one scalar-bearing `value_token_id`. Optional lists identify condition, statistic, and table/figure-reference tokens. Conditions must be numeric ledger tokens in the **same source statement** as the selected value. Multiple adjacent condition tokens produce the verbatim substring from the first selected start to last selected end. This is deliberately strict to prevent borrowing a dose, cohort, temperature, or time point from another sentence.

- `scalar` and `units` come directly from the value token.
- A p/n/CI value token supplies its own statistic. Additional selected statistic tokens supply their full exact statistic or raw text. One statistic is emitted as a string; multiple are emitted as an array without joining or normalization.
- The comparator is the selected exact comparator. Distinct selected comparators are rejected.
- Condition tokens may not cross statements, even when both statements are in the same paragraph. This rejects cross-condition decoys mechanically, although same-statement semantic errors still require Agent review.
- Statistic and table/figure references may have separate statement-level evidence because the script cannot prove their semantic attachment. Select them only after source reading explains the attachment.

### Not reported

Use `not_reported` only when the requested information is absent in the actually readable, task-defined scope. It is never the default after a failed regex match and never numeric zero. It requires explicit coverage:

```json
{
  "status": "not_reported",
  "coverage": [
    {
      "source_id": "main-paper",
      "paragraph_id": "p-methods",
      "quote": "Exact searched sentence or row with its scope…",
      "start": 120,
      "end": 184
    }
  ],
  "notes": "What was inspected and why this is absence, not unreadability"
}
```

`start` and `end` can be omitted only if the exact quote occurs once in the paragraph. Otherwise both are mandatory. An explicit “did not report” sentence is ideal but not required; broader coverage and precise notes may support an absence reading. A script cannot prove document-wide semantic absence, so the audit states this boundary.

### Source conflict

Use `source_conflict` when two or more genuinely applicable readings disagree. Preserve every variant:

```json
{
  "status": "source_conflict",
  "variants": [
    {"status": "reported", "value_token_ids": ["N000005"], "condition_token_ids": ["N000004"], "notes": "Primary source"},
    {"status": "reported", "value_token_ids": ["N000016"], "condition_token_ids": ["N000015"], "notes": "Replication"}
  ],
  "notes": "Exact disagreement; no preferred value or average"
}
```

Variants must have identical lexical experimental-condition strings so that a conflict cannot disguise different cohorts or conditions. Their exact scalar/unit/statistic/comparator representations must differ. Top-level scalar, units, statistic, comparator, paragraph, and quote remain `null`; `result.fields[*].conflicts` retains each complete variant. If equivalent conditions differ typographically, the conservative builder refuses to merge them—record an `extraction_failed`/`ambiguous_scope` limitation rather than silently normalizing.

### Extraction failed

`extraction_failed` covers `pending_read`, `no_text_layer`, `ocr_unreadable`, `unreadable_source`, `parse_error`, `missing_material`, `ambiguous_scope`, or another explicit `failure_kind`. It has null value fields and mandatory notes. Coverage is optional when no readable quote exists. This status must remain distinguishable from semantic absence and genuine source disagreement.

## Build and check

```sh
python3 -B scripts/numeric_result.py build \
  --case examples/minimal/input/case.json \
  --targets examples/minimal/input/target-fields.json \
  --sources examples/minimal/input/sources.json \
  --ledger examples/minimal/output/numeric_ledger.jsonl \
  --selection examples/minimal/selection.json \
  --output examples/minimal/output/result.json \
  --audit examples/minimal/output/audit.md
```

Use the same arguments with `check` instead of `build` to reconstruct the expected JSON and reject any altered scalar, unit, statistic, condition, comparator, quote, evidence, ledger IDs, or other result content. `check` never repairs the submitted file.

## Result shape

Top-level keys are `case_id`, `status`, `result`, `claims`, `uncertainties`, plus `sources` and `change_records`. Overall status is:

- `answered`: every requested field has a completed adjudication (`reported`, scoped `not_reported`, or documented `source_conflict`) and at least one is `reported`;
- `partial`: at least one field is `extraction_failed` but at least one is `reported`, or the early `pending_read` partial is still in progress;
- `insufficient_evidence`: no field is `reported` and fields are failed or all are scoped non-reports;
- `input_error`: malformed or missing required input.

`result.fields` contains exactly one record per requested `field_id`. If `result.field_results` is included by another adapter, it must be identical. Every field record includes:

| Key | Rule |
|---|---|
| `field_id` | Exact requested ID |
| `status` | `reported`, `not_reported`, `source_conflict`, or `extraction_failed` |
| `scalar`, `units`, `statistic` | Exact token-derived strings/arrays or `null`; no conversion or invented values |
| `experimental_condition`, `condition` | Exact grounded condition text in both keys, or `null` |
| `comparator` | Exact comparator or `null` |
| `paragraph_id`, `quote` | Exact primary source anchor or `null` for unresolved/multi-anchor conflict |
| `evidence` | List of `source_id`, `page`, `paragraph_id`, `quote`, statement/token IDs and exact spans |
| `notes` | Semantic binding, absence, failure, or conflict explanation |
| `ledger_ids` | Value/condition/statistic/reference IDs used in construction |

Conflict records additionally have `conflicts`; failed records additionally have `failure_kind`. `claims` quotes reported/conflicted evidence without inferring an unstated scientific conclusion. `uncertainties` carries each unresolved field and preserves conflict alternatives. `change_records` records selection and ledger SHA-256 hashes and explicitly marks conversion and similarity ranking as false.
