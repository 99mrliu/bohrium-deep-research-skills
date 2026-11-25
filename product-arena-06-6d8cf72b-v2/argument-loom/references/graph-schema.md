# Graph and anchor schema

This reference defines the interoperable JSON representation used by `scripts/argument_loom.py`. It is deliberately smaller than a general ontology and keeps review semantics visible.

## Source registry

A source JSON object has:

- `source_id`: stable ID shared by graph anchors;
- `title`: supplied document title;
- `status`: `readable`, `partial`, or `unreadable` (a missing source should be reported in case-level status rather than fabricated as a registry entry);
- `sections`: ordered objects with unique `section_id`, integer `order`, `title`, `purpose`, and `paragraphs`;
- each paragraph has a unique-within-section `paragraph_id` and source `text`;
- optional `synthetic: true` on the source (or case) explicitly enables synthetic/non-official output banners; absence means real/non-synthetic.

The normalized paragraph is `re.sub(r"\s+", " ", text).strip()`. A locator has the form `section_id/paragraph_id`. Anchor quotes and offsets refer to that normalized paragraph, not to a PDF byte stream. In production, page/line information may be retained in paragraph metadata and the source registry may be generated from actual `pdftotext`/OCR output; never silently replace unreadable text with guesses.

## Anchors

Every substantive node has an `anchor` object:

```json
{
  "source_id": "paper-a",
  "locator": "results/p1",
  "quote": "mean peak temperatures were 18.0 °C and 20.0 °C",
  "start": 42,
  "end": 100,
  "page": 2
}
```

`quote` must be a nonempty, contiguous, verbatim substring after the same whitespace normalization, at most 240 Unicode characters. `start` is zero-based and inclusive; `end` is exclusive. Both must be absent or both present; when present, slicing the normalized paragraph must exactly reproduce `quote`. Offsets disambiguate repeated language. `page` is optional and should be the PDF page when known. Do not join noncontiguous phrases with ellipses and call the result verbatim.

The audit checks these mechanics only. A matching quote can still fail to entail a node, so `semantic_status` records `unreviewed`, `reviewer_confirmed`, or `disputed` separately.

## Graph

Top-level fields:

- `graph_id`, `paper_id`, `example_label`, `source_id`;
- `sections`: the ordered section inventory used by the graph, including each section purpose;
- `nodes`: typed nodes;
- `edges`: directed typed relations;
- `uncertainties`: strings for unresolved reading or interpretation;
- `change_records`: objects with `action` and `detail` strings.

Node fields are `id`, `type`, `text`, `section_id`, `section_order`, `anchor`, and `semantic_status`. Types are:

- `claim`: an assertion; add `core: true` for claims that require coverage audit;
- `evidence`: an observation, measurement, analysis, table, or figure result;
- `warrant`: the methodological or inferential reasoning that licenses evidence-to-claim movement;
- `limitation`: a bound on scope, certainty, measurement, or generalization;
- `transition`: an explicit move between sections or argumentative stages;
- `background`: context or prior-work framing.

A core claim additionally has `limit_status`: `reported`, `not_reported`, or `not_applicable`. Use `reported` only when at least one incoming `limits` edge connects a limitation node. `not_reported` means a readable source does not state a limitation for that claim; it does not mean no limitation exists. `not_applicable` needs justification in `uncertainties` and should be rare for empirical claims.

Edge fields are `id`, `from`, `to`, and `type`. Relations and endpoint rules:

| Edge | From → To | Meaning |
|---|---|---|
| `supports` | evidence → claim | Evidence is offered for the claim |
| `warrants` | warrant → claim | Reasoning licenses the inference |
| `limits` | limitation → claim | Limitation bounds the claim |
| `motivates` | claim/background → claim | Earlier move motivates a later one |
| `transitions_to` | transition → claim/background | Explicit bridge into a later move |

No self-edges or duplicate IDs are allowed. Every referenced node must exist and every non-claim node must participate in an edge. `motivates` and `transitions_to` must point to a node in the same or a later section; their subgraph must be acyclic. This prevents apparent argumentative progress from secretly moving backward. The source section order and graph `section_order` must agree.

For every `core: true` claim, the audit requires at least one incoming `supports`, one incoming `warrants`, and a coherent limit status. A `disputed` semantic status generates a warning rather than being erased. A `PASS` therefore means structurally auditable, not scientifically true or complete.

## Result contract

The assembler reads the case's `output_contract` and constructs only allowed fields. Use optional `assemble --response response.json` for a JSON object containing direct answers and other contract-specific declared fields; it is merged with generated graph/output/source/uncertainty/change data. Every declared top-level property must be assembled even if omitted from `required`. Closed contracts reject undeclared response keys. The overall status honors the status enum (`success` or `complete` for a fully readable, reviewed graph; `partial`; `failed`) and cannot be upgraded by the overlay when source recovery or core-claim review is open.

The checker supports nested objects/arrays, `required`, `properties`, `additionalProperties: false`, scalar types, `enum`, `const`, length/item bounds, numeric bounds, `pattern`, `anyOf`, and `uniqueItems`. Unsupported schema keywords fail explicitly instead of being silently ignored. Output paths are bundle-relative or output-root-relative strings, never personal absolute paths. On graph validation/loading failure, assembly writes a contract-valid failed result when the status vocabulary permits and preserves parseable input without fabricating replacement graph content.
