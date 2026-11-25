# Agent-authored `bindings.json` schema

Top-level object:

- `schema_version`: `symbol-scope-bindings-1`.
- `case_id`: exact case ID copied from `case.json` and ledger.
- `requested_status`: normally `complete` or `partial`; validation can downgrade
  it and no-formula cases prefer `insufficient_evidence`.
- `symbol_bindings`: array of scoped symbol decisions.
- `formula_coverage`: one entry per formula occurrence.
- `limitations`: array of honest source/analysis limitations.
- `notes`: optional analysis note.
- `output_fields`: optional object keyed by exact case-specific contract fields.
  Built-in fields (`case_id`, `status`, `variables`, `formula_coverage`, and so
  on) are generated from checked analysis and should not be overwritten.

Minimal direct binding shape (illustrative identifiers only):

```json
{
  "symbol_instance_id": "sym-000001",
  "section_id": "doc-0001-sec-0001",
  "canonical": "r_{1}",
  "base_glyph": "r",
  "scripts": {"sub": "1"},
  "meaning": "the meaning supported by the defining clause",
  "category": "direct_source_definition",
  "selected_candidate_id": "cand-000001",
  "evidence": {
    "quote": "Exact candidate quote copied without ellipsis or paraphrase.",
    "locator": {
      "document_id": "doc-0001",
      "section_id": "doc-0001-sec-0001",
      "paragraph_id": "p-000001",
      "sentence_id": "s-000001",
      "source_pointer": "/article[1]/body[1]/sec[1]/p[1]"
    }
  },
  "unit": {
    "value": null,
    "provenance": "not_reported",
    "reason": "No unit appears in this local source scope."
  },
  "range": null
}
```

A range can instead be an object with `lower`, `upper`, and optional `text`; its
literal provenance quote must support all populated bounds. A unit's value is its
unit label, not a guessed numerical magnitude. A numerical quantity that does
not exist in source must remain null.

Formula coverage shape:

```json
{
  "formula_id": "f-000001",
  "covered": true,
  "excluded": false,
  "symbol_instance_ids": ["sym-000001"],
  "reason": "How this occurrence was reviewed."
}
```

For an exclusion use `covered: false`, `excluded: true`, an empty or applicable
symbol list, and a specific reason. `covered: null` is deliberately invalid.

For a conflict binding, set `category: "conflict"` and supply:

```json
"conflicts": [
  {
    "claim": "First incompatible meaning",
    "candidate_id": "cand-000001",
    "quote": "Exact first candidate quote",
    "locator": {"sentence_id": "s-000001", "section_id": "doc-0001-sec-0001"}
  },
  {
    "claim": "Second incompatible meaning",
    "candidate_id": "cand-000002",
    "quote": "Exact second candidate quote",
    "locator": {"sentence_id": "s-000002", "section_id": "doc-0001-sec-0001"}
  }
]
```

In a real submission copy each locator **in full** from its candidate; the short
object above only illustrates fields. The validator requires exact equality with
the selected candidate locators for conflicts and direct definitions.
