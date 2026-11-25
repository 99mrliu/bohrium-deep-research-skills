# Agent-created case specification

The runner consumes an agent-created specification; it does not infer an official answer from a domain label. Specification `schema_version` is `1`, `case_id` must exactly match the actual case, and `mode` is one of `chart`, `diagram`, or `svg_edit`.

## Common fields

```json
{
  "schema_version": 1,
  "case_id": "actual-case-id",
  "title": "Source-bound title",
  "mode": "chart",
  "artifact_key": "the actual SVG output_contract key",
  "preview_artifact_key": "the actual PNG output_contract key",
  "pdf_artifact_key": "the actual PDF output_contract key when present",
  "data_artifact_key": "the actual JSON output_contract key",
  "report_artifact_key": "the actual report output_contract key",
  "materials": [
    {
      "id": "unique-source-id",
      "path": "/input/actual-file.csv",
      "kind": "csv",
      "role": "primary_source",
      "version": "source-provided-version-or-unversioned",
      "locator": "actual sheet/page/figure/region"
    }
  ]
}
```

The five artifact role fields are required when the contract has more than one artifact of a kind, and are recommended always. They must name original `output_contract` keys, not newly invented aliases. Omitting a role allows deterministic first-of-kind detection; an auxiliary report/PNG/data path is created only if that kind is absent. An auxiliary `preview.pdf` is created only for `--preview-pdf` when no PDF contract key exists.

A PDF output is declared like any other dynamic contract entry, for example `"printable → PDF": {"path": "figure.pdf", "kind": "pdf", "required": true}` plus `"pdf_artifact_key": "printable → PDF"`. `.pdf` also infers `kind: pdf`. PNG and PDF default to optional when `required` is omitted. A required PDF is exported even without `--preview-pdf`; an optional PDF is exported only with that flag. No PDF is created for an unrequested optional entry, and its top-level result value remains `null` with availability `not_requested`.

Material kinds are descriptive (`csv`, `text`, `pdf`, `png`, `svg`, or another source type). Every material path is read and hashed. Relative paths resolve against `spec.json`; absolute paths are preferred at official runtime. A missing source remains missing in the manifest. If a source version is not present in the input, use `unversioned`, not a guessed publication/version identifier.

## `chart`: actual columns and rows

```json
"chart": {
  "source_id": "unique-source-id",
  "x_column": "exact CSV header",
  "y_column": "exact response header",
  "series_column": "exact condition header",
  "title": "Observed response by condition",
  "x_label": "Time (min)",
  "y_label": "Response (source units)"
}
```

`series_column` is optional. `x_column` and `y_column` must exist exactly and contain finite numeric values. Duplicate headers or excess row fields are `ambiguous`; missing headers and invalid numbers are `semantic_defect`; no usable rows is `missing_material`. The fallback line chart connects points in **source CSV order**, grouped by first appearance of series. It does not sort, smooth, interpolate, fit, or silently rename values.

`data_mapping.json` retains exact header names, raw cell strings, parsed coordinates, series, and source row numbers (header is row 1). Its `primary_source_comparison.rows` compares each plotted coordinate to the same parsed CSV cell. This is a data transfer comparison, not a claim of scientific validity or external replication.

## `diagram`: inspected entities and relationships

```json
"diagram": {
  "entities": [
    {"id": "entity-a", "label": "Label visible in the actual source"},
    {"id": "entity-b", "label": "Second observed label"}
  ],
  "edges": [
    {"from": "entity-a", "to": "entity-b", "label": "visible relationship"}
  ]
},
"figure_inspection": {
  "figure_id": "figure03",
  "source_id": "actual-pdf-material-id",
  "page": 3,
  "region": "full figure or observed panel names",
  "observations": [
    "Entity labels actually inspected",
    "Arrows/connectors actually inspected, including direction"
  ],
  "uncertainties": ["Any unreadable label or unresolved relationship"]
}
```

The layout uses deterministic grid positions and editable SVG groups. Entity IDs must be unique and edge endpoints must exist. `figure03` with no observations produces `missing_material`; it is not licensed to fill a familiar biological pathway from memory. The agent's inspection is preserved in the report and source record. Scientific judgement remains the agent/native evaluator's role, not a renderer pass.

## `svg_edit`: source-preserving targeted patch

```json
"svg_edit": {
  "source_id": "original-svg-material-id",
  "replacements": [
    {
      "target_id": "existing-element-id-for-human-traceability",
      "old": "<exact existing literal substring>",
      "new": "<replacement literal substring>",
      "expected_count": 1
    }
  ]
}
```

`old` must be nonempty. The default expected count is 1. Zero matches is a `semantic_defect`; a different count is `ambiguous` (an invalid noninteger/nonpositive count is also a semantic defect). Replacements run sequentially over literal text. There is no XML parse/serialize cycle, wholesale template substitution, repositioning, font rewrite, or recreation of unaffected elements. The original source is never overwritten. Change records contain source/output SHA-256 and every patch. For geometry or broad redesign needs, admit the limitation rather than rebuilding an existing SVG under the guise of an edit.

## Errors and scientific restraint

Do not add an entity because it is typical, a control because it is expected, a number because an axis looks empty, or a relation because it makes the layout simpler. Use observations from the actual materials and put unresolved points in `uncertainties`. The runner handles delivery and mechanical source mapping; it does not replace native scientific review.
