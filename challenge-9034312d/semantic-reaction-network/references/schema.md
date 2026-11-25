# Semantic graph and result schema

The executable schema version is `semantic-reaction-network/1.0`. The complete runnable instance is `examples/synthetic/input/semantic_graph.json`; it is synthetic and must not be copied as an official answer.

## Top-level graph fields

- `schema_version`, `case_id`, `title`: required identity. `synthetic: true` is mandatory for bundled examples only.
- `sources`: `{id, role, path, version?, locator?}`. Paths resolve relative to the graph JSON. Record only supplied versions.
- `primary_biological_source`: `{required, figure, caption, methods}` source IDs. For real primary-biological cases use `required: true`; an unavailable item produces partial delivery.
- `source_review`: actual inspection status and figure/caption/methods paths/locators.
- `compartments`: ordered `{id,label,columns?}`. `columns` affects layout only.
- `nodes`: stable IDs; `kind`, `label`, `compartment` where applicable, `required`, `source_refs`, `ports`; optional `entity_type`, `phase`, `measured_property`, `chart`.
- `edges`: stable IDs; `kind`, `from:{node,port}`, `to:{node,port}`, `source_refs`, optional `phase`, `label`, `condition`, `feedback`, and `visual.marker`.
- `phase_dependencies`: sourced phase pairs and `type` (normally `precedes`).
- `branches`, `joins`: `{id,node,family,mode,edge_ids,source_refs}`; family is `material` or `sequence`.
- `source_semantics`: original required nodes, directed typed edges, and phases for source-to-final comparison.
- `change_records`: actual edits/layout decisions with source evidence.
- `output_contract`: target relative filenames. The runtime may supply extra keys; they must survive into the result top level even when null/partial.

## Ports and markers

Ports: `{id,direction:in|out,carrier:material|control|signal|data}`. The renderer derives scientific styles from `kind`; activation nonetheless requires `visual.marker: activation-arrow` and inhibition `inhibition-bar` in the graph so wrong generic-arrow encodings fail early. Other kinds may use the markers shown in the synthetic graph.

## Chart node

```json
{
  "id": "chart",
  "kind": "chart",
  "label": "Source-data panel B",
  "required": true,
  "source_refs": ["figure03", "measurement_csv"],
  "ports": [{"id": "data_in", "direction": "in", "carrier": "data"}],
  "chart": {
    "csv_path": "source_data.csv",
    "x": "actual_x_header",
    "y": "actual_y_header",
    "series": "actual_series_header_or_null",
    "x_label": "time (min)",
    "y_label": "product (µM)",
    "panel": "B",
    "source_refs": ["measurement_csv"]
  }
}
```

All CSV rows parsed are charted in first-appearance series order and sorted within each series by numeric x then original CSV line. No aggregation, interpolation, smoothing, inference, or hidden filtering occurs. The output semantic graph includes headers, row count, CSV path/SHA-256, and exact mapping; SVG circles retain `data-csv-line`, `data-x`, `data-y`, and series grouping.

## result.json

Required top-level fields:

- original `case_id` and **every original output-contract key**, not nested only under `paths`;
- `status`: `success`, `partial`, `failed`;
- `sources`: inventory with availability and hashes where possible;
- `uncertainties`: missing evidence, inspection limits, export failures, or unproduced contract outputs;
- `change_records`: targeted edits, source-supported corrections, layout-only changes;
- `paths`: actual generated paths or null, relative to the output directory for contained artifacts (external explicit CLI paths may be absolute);
- schema version, semantic summary, and export checks may be added.

Contract keys used by `srn.py`: `editable_svg`, `preview_png`, `preview_pdf`/`export_pdf`, `export_report`, `semantic_graph`, `validation_report`, `source_comparison`, and `result_json`. Conventional PDF keys and any other string contract value ending in `.pdf` request validated PDF export. Other contract keys remain top-level and are linked when a file exists, otherwise null with a partial uncertainty. PDF paths are linked only after a fresh structurally checked export, never merely because a stale file exists. At official runtime, adapt graph `output_contract` exactly to the case's original contract and produce other requested deliverables separately. Never drop a contract key because generation failed.
