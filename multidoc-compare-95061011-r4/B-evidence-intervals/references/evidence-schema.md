# Evidence interval JSON schema (normative guidance)

The evidence file is a UTF-8 JSON object with `schema_version` and `records`. No scientific values are predefined by the tools.

```json
{
  "schema_version": "1.0",
  "records": [
    {
      "evidence_id": "unique-id",
      "comparison_id": "comparison-from-workorder",
      "task": "task wording or exact task_id from workorder",
      "source_document_id": "document-stem",
      "paragraph_id": "document-stem-p0002",
      "page": 1,
      "field": "adsorption_capacity",
      "material": "exact material name",
      "pollutant": "exact pollutant name",
      "metric": "adsorption_capacity",
      "value": 128.0,
      "value_literal": "128",
      "unit": "mg/g",
      "budget": "exact denominator and conditions",
      "value_type": "direct",
      "status": "confirmed",
      "comparability": "comparable-record-level",
      "qualifier_evidence": {
        "material": ["ctx-a"],
        "pollutant": ["ctx-a"],
        "metric": ["def-a"],
        "unit": ["sup-a"],
        "budget": ["ctx-a"]
      },
      "source_spans": [
        {
          "span_id": "sup-a",
          "role": "support",
          "source_document_id": "document-stem",
          "paragraph_id": "document-stem-p0002",
          "page": 1,
          "start": 0,
          "end": 42,
          "quote": "exact original paragraph slice",
          "content_sha256": "paragraph SHA-256"
        },
        {
          "span_id": "ctx-a",
          "role": "context",
          "source_document_id": "document-stem",
          "paragraph_id": "document-stem-p0001",
          "page": 1,
          "start": 0,
          "end": 80,
          "quote": "exact original condition paragraph",
          "content_sha256": "paragraph SHA-256"
        }
      ],
      "derivation": null,
      "search_scope": null,
      "conflict_group": null,
      "uncertainty": "none identified"
    }
  ]
}
```

## Record rules

- `evidence_id` must be unique. `source_document_id` is the source filename stem without an extension and never an arbitrary alias.
- `paragraph_id` and `page` at record level identify the support paragraph for direct, derived, and inference records. For absent records, `paragraph_id`, `page`, and source spans are null/empty.
- Required common qualifiers are `task`, `comparison_id`, `field`, `material`, `pollutant`, `metric`, `unit`, and `budget`. The workorder may add common fields.
- `value_type` is `direct`, `derived`, `inference`, or `absent`. Absent uses the string `not_reported`; other value types use a JSON number for numeric synthesis. An absent record must use `status: not_reported`.
- `comparability` is a label, not permission to pool. Use `noncomparable` where appropriate; it does not by itself alter run status.

## Span rules

- `span_id` is unique within a record. Roles are `support`, `context`, or `definition`.
- `start`/`end` are zero-based Unicode code-point offsets in the indexed paragraph and `end` is exclusive.
- `quote` must match that exact slice after normalized equivalence. `content_sha256` is the indexed paragraph hash, not a hash of only the quote.
- Page, document, and paragraph locators occur on every span even if the same paragraph is reused.
- One quantitative record has exactly one support span and at least one context span. Definition spans are optional unless needed to interpret the metric.
- `qualifier_evidence` values are lists of span IDs. Each referenced span must literally contain the corresponding record qualifier after normalization. Multiple spans may jointly establish a long condition only if each declared containment test still passes; do not use a span that lacks the qualifier.

## Derived records

```json
"derivation": {
  "formula": "(retained_mass / adsorbent_mass)",
  "result_unit": "mg/g",
  "justification": "Both operands describe the same sealed experiment.",
  "operands": [
    {
      "name": "retained_mass",
      "value": 512.0,
      "value_literal": "512",
      "unit": "mg",
      "source_span_id": "sup-b"
    },
    {
      "name": "adsorbent_mass",
      "value": 4.0,
      "value_literal": "4",
      "unit": "g",
      "source_span_id": "sup-b"
    }
  ]
}
```

Operand names in the formula must be declared exactly once. Span references must resolve and literals must occur in those spans. The evaluator permits only arithmetic, not function calls or names outside the operand set. `result_unit` must equal the record unit. Justification must explain why operands belong to the same experiment and why the requested unit follows.

## Absence records

```json
{
  "value_type": "absent",
  "value": "not_reported",
  "value_literal": null,
  "paragraph_id": null,
  "page": null,
  "source_spans": [],
  "qualifier_evidence": {},
  "search_scope": {
    "source_document_id": "document-stem",
    "paragraph_ids": ["every indexed paragraph in this document"],
    "queries": ["adsorption capacity", "q_e", "equilibrium capacity"],
    "corpus_sha256": "document content hash from source-index.json"
  }
}
```

`not_reported` claims only that the specified field was not found in that searched document scope. It does not prove universal nonexistence. Retain scope and search limitations in result uncertainty.

## Conflict records

Use the same non-empty `conflict_group` on every conflicting record and set `status: conflicted`. Each record retains its own intervals and value. Add record-level uncertainty explaining the disagreement. The validator detects unlabelled conflicting values and rejects singleton conflict groups.
