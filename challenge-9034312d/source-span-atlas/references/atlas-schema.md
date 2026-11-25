# Source-span atlas schema (source-span-atlas/1.0)

The authoritative runnable example is `examples/minimal/input/atlas.json`. This reference explains the contract; it is not a prepared answer for an official case.

## Root fields

- `schema_version`: exactly `source-span-atlas/1.0`.
- `case_id`: copied exactly from actual `/input/case.json`.
- `synthetic`: must be `true` for the bundled examples; normally omitted/false for a real case.
- `title`: visible figure title.
- `sources[]`: actual source inventory.
- `assertions[]`: source-backed scientific/visual claims; no best-guess placeholder flows.
- `figure_reviews[]`: direct original-figure inspection records, when applicable.
- `charts[]`: actual CSV-to-chart bindings, when applicable.
- `conflicts[]`: discovered source/source or source/figure conflicts. Empty means none were recorded, not that absence was proven.
- `uncertainties[]`: honest limitations, omissions, ambiguity, missing materials, font/export risks.
- `change_records[]`: generation can use `[]`; edits should include targeted before/after records.
- `output_contract`: copy the actual case's object. Its **every key must also appear at `result.json` top level**, never only beneath a nested `output_contract` field. Values in the example are desired output filenames; the runtime agent maps actual contract values according to the task.

## Source records

```json
{
  "source_id": "methods",
  "path": "sources/methods.txt",
  "kind": "methods",
  "version": "PDF filename + extraction hash or publisher version",
  "role": "Actual methods source",
  "original_pdf_page_offset": 0
}
```

`kind` is `methods`, `text`, `figure`, or `csv`. Relative `path` is resolved against the atlas JSON's directory, never the caller's working directory. Absolute `/input`, `/app/work`, or `/app/output` paths are allowed at runtime. UTF-8 BOM is tolerated and excluded from hashing; invalid UTF-8/NUL fails.

For a binary original Figure 03/PDF, use a real UTF-8 caption/transcript/extraction at `path`, plus:

```json
{
  "source_id": "figure03",
  "path": "sources/figure03-caption.txt",
  "kind": "figure",
  "visual_path": "/input/original-figure03.png",
  "visual_sha256": "actual binary SHA-256"
}
```

The validator hashes the actual `visual_path` bytes and requires the direct review to cover that same hash. A transcript is not a substitute for seeing `visual_path`; it only gives an exact textual anchor. For a text-native SVG original, `path` can itself be the SVG and `visual_path` can be omitted, as in the synthetic fixture.

PDF text must preserve form-feed page separators. `page` is computed from form feeds (one-based). If printed page numbers differ from extracted page positions, keep the computed extraction `page`, record `printed_page` separately in the locator, verify against a rendered PDF page, and explain `original_pdf_page_offset` rather than silently renumbering.

## Assertions and evidence statuses

```json
{
  "id": "A_FLOW_01",
  "category": "connection",
  "label": "Valve to detector",
  "from": "visual-valve",
  "to": "visual-detector",
  "evidence_status": "explicit",
  "visual": {"id": "visual-edge-01"},
  "evidence": [
    {
      "source_id": "methods",
      "quote": "An exact sufficiently long source excerpt.",
      "locator": {"page": 2, "section": "2.3 Apparatus", "printed_page": 4}
    }
  ],
  "semantic_review": {
    "result": "match",
    "reviewed_sources": ["methods"],
    "reviewer": "native-agent actual PDF comparison",
    "comparison": "Explain source meaning versus this exact visual meaning."
  }
}
```

Allowed `category`: `entity`, `connection`, `step`, `stage`, `data`, `note`.

- **explicit**: directly supported by the quoted source in the stated context. Requires evidence and a separate semantic match.
- **inferred**: non-source inference only when a task legitimately permits it. Requires evidence, `inference_rationale`, semantic review, a dashed display, and an uncertainty. The core deliberately rejects inferred **connections**; omit an unreported connection or ask for clarification instead. Do not use `inferred` as a licence to complete a plausible apparatus.
- **unsupported**: always fails the gate. Do not render it. A failed report can document the blocked claim; a subsequent passing atlas must remove the affirmative claim and disclose the omission/uncertainty. There is no factual waiver.

Each explicit/inferred assertion needs one or more unique textual evidence spans. Quote matching is exact after the documented normalization, with no fuzzy/similarity acceptance. If the same normalized quote occurs multiple times, lengthen it with surrounding source context; never pick an arbitrary occurrence. A `locator` requires a computed `page` and a nonempty `section` or `figure`; figure evidence should also include `panel`. Optional `line_start`/`line_end` are checked against the actual match.

The output atlas records the original excerpt, original code-point `[start,end)`, normalized span, page, line range, locator, source SHA-256, and match rule. Code-point offsets apply to the decoded original source, not bytes. NFKC expansion and folded whitespace explain why normalized and original offsets can differ.

## Separate semantic review

`semantic_review.result` must be `match` for rendered claims. `mismatch`, `unreviewed`, or missing review fails. `comparison` must compare meaning, not merely state “quote found”. `reviewed_sources` must include every evidence source and any CSV visually interpreted. `reviewer` records the native agent/person review identity.

This field is an auditable attestation, not automated proof of science. The agent must actually inspect the PDF context and original figure geometry before asserting `match`. See `semantic-and-figure-review.md`.

For a figure-backed assertion, include `figure_review_id` pointing to a direct visual review. Figure reviews require:

```json
{
  "figure_review_id": "F03_DIRECT_REVIEW",
  "source_id": "figure03",
  "inspection_mode": "direct_visual",
  "inspected_panels": ["a", "b"],
  "reviewed_sha256": "hash of visual_path bytes, or textual figure source if no visual_path",
  "reviewer": "native visual inspection",
  "comparison": "Actual geometry, arrows, panel identity, labels and omissions versus the proposed visual."
}
```

## Connections and ordering

A `connection` needs `from`/`to` equal to declared node visual IDs, not other edges. The arrow means the relation verified in the semantic review; source prose merely saying two nouns occur together does not establish direction. A `step` needs a unique positive integer `order`; any arrow between steps must be its own source-backed assertion. No inferred cycle, branch, return, bypass, or waste outlet is allowed.

## Real CSV bindings

```json
{
  "id": "chart-response",
  "assertion_id": "A_RESPONSE_CHART",
  "source_id": "measurements",
  "x_column": "time_s",
  "y_column": "response",
  "title": "Actual source values",
  "x_label": "time_s — seconds",
  "y_label": "response — arbitrary units"
}
```

The chart ID must equal its data assertion's `visual.id`. CSV column names are case-sensitive and must exist exactly. Duplicate/empty headers, ragged rows, missing data, and nonnumeric/nonfinite plotted values fail. Output preserves raw strings, numeric values, actual one-based file row numbers including the header, source hash, and target visual ID. The core draws only a simple two-numeric-column line/scatter chart, in CSV order. It does not fit, impute, aggregate, transform units, infer series, or manufacture error bars.

## Conflicts

```json
{
  "id": "X01",
  "status": "unresolved",
  "assertion_ids": ["A_FLOW_01"],
  "source_ids": ["methods", "figure03"],
  "description": "Actual disagreement",
  "resolution": "Required when resolved",
  "visual_treatment": "Required when resolved"
}
```

`unresolved` fails the gate. `resolved` needs a source-grounded explanation and visual treatment. Never silently choose the more recent, longer, prettier, or expected-looking source. If contradiction concerns direction/identity/order, leave the relevant element out and return partial/failed with an uncertainty unless the actual sources support a resolution.

## SVG coverage

Every assertion must map to one unique XML `id`. Every scientific SVG group must have `data-scientific="true"`, `data-assertion-id`, `data-evidence-status`, and `data-source-ids`. The gate checks both directions: no missing/mismatched assertion visuals, no orphan scientific groups, no duplicate IDs. Layout/title/background/legend groups are non-scientific and do not bypass evidence accounting.
