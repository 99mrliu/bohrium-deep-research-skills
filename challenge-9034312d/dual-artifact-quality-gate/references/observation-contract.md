# Independent observation contract

`artifact_observer.py` reads only the supplied SVG and CSV files. It does not import the
fixture renderer and has no CLI option for an IR, truth table, expected matrix, or source
answer. Its output is a structural observation, not scientific validation.

## SVG conventions

Use these attributes on visible SVG elements. IDs must be unique within each observed kind.
The parser leaves other valid SVG intact; unannotated visible text is still collected, but
semantic checks requiring an ID then fail rather than guessing.

### Editable layers

Use real groups with `data-qc-layer` names and/or Inkscape layer labels:

```xml
<g id="entities" data-qc-layer="entities" inkscape:groupmode="layer"
   inkscape:label="Entities">...</g>
```

### Entities and visible labels

Put the observation attribute on a group that contains a visible `<text>` or on any element
with a visible text descendant:

```xml
<g data-qc-kind="entity" data-qc-id="reactor">
  <rect x="300" y="150" width="150" height="70" fill="#d9ebea"/>
  <text x="375" y="190">REACTOR</text>
</g>
```

The observer records ID, concatenated visible label, layer ancestry, fill/stroke/style and
bounding geometry when directly available. Do not put the answer only in an invisible
`<title>` or metadata block.

### Directed relationships and numbering

```xml
<path data-qc-kind="edge" data-qc-id="feed_to_pump"
      data-from="feed" data-to="pump" data-order="1"
      d="M120 190 L265 190" stroke="#33445a" stroke-width="3"
      marker-end="url(#arrow)" fill="none"/>
```

The observer records endpoints, order, marker-start/mid/end, path data and style. Marker IDs
come from the actual `marker-end` attribute, not an IR. The agent must visually inspect the
marker definition and placement; `url(#arrow)` alone does not prove the triangle is visible
or points the right way.

### Legend/style

```xml
<g data-qc-kind="legend-item" data-qc-id="flow" data-target="feed_to_pump">
  <line x1="50" y1="350" x2="90" y2="350" stroke="#33445a"
        stroke-width="3" marker-end="url(#arrow)"/>
  <text x="100" y="356">MATERIAL FLOW</text>
</g>
```

The observer records target, visible label and style from the group and direct graphical
child. Expect legend style and target style separately when needed.

### Chart values

Put one observation attribute on each visible mark (rect, circle, path, line or group):

```xml
<rect data-qc-kind="chart-value" data-qc-id="Measurement|Run A"
      data-series="Measurement" data-key="Run A" data-value="2.5"
      data-unit="units" x="480" y="170" width="45" height="120"
      fill="#527a9e"/>
```

The observed key is `chart_values` followed by the ID. `data-value` must describe the value
visually encoded by that mark; geometry (x/y/width/height/cx/cy/r/d) is also recorded so that
matrix rows and reviewers can cross-check scales. A metadata value without a visible mark is
invalid. The observer does not digitize arbitrary axes automatically; for unsupported charts,
add an honest manual observation limitation and visually compare the original chart.

### Sequence and other expectations

Text content can include visible step numbers. Use `data-order` for a machine observation and
also inspect visible numbering. The observer additionally emits `texts`, `layers`, `layer_set`,
`text_count`, `view_box`, `width`, `height`, `element_count`, and `ids`.

## Output shape

```json
{
  "schema": "dual-artifact-quality-gate/observations-v1",
  "observer": "artifact_observer.py",
  "independence": "SVG/CSV only; no IR, truth table, expected matrix, or renderer import",
  "svg": {
    "path": "figure.svg",
    "sha256": "...",
    "entities": {"reactor": {"label": "REACTOR", "layer": "entities"}},
    "edges": {"feed_to_pump": {"from": "feed", "to": "pump", "marker_end": "arrow", "order": 1}},
    "legend_items": {},
    "chart_values": {},
    "layers": [],
    "layer_set": [],
    "texts": [],
    "text_count": 0,
    "view_box": [0, 0, 800, 450],
    "element_count": 40
  },
  "csv": {
    "measurements.csv": {
      "path": "measurements.csv",
      "sha256": "...",
      "columns": ["series", "category", "value", "unit"],
      "rows": [{"series": "Measurement", "category": "Run A", "value": "2.5", "unit": "units"}],
      "values": {"Measurement|Run A": {"value": 2.5, "unit": "units", "row": 2}}
    }
  },
  "parser_limitations": []
}
```

For CSV, columns named `series`, `category`/`key`, `value`, and optional `unit` produce keyed
numeric observations. A duplicate series/category key is a parser limitation and keeps the
first value; do not silently average duplicates. Other CSVs still expose columns and rows.
Numeric conversion accepts ordinary JSON decimal numbers only; nonnumeric source cells remain
strings and should be reviewed rather than coerced.

## Matrix paths and operators

Paths are dot-separated dictionary keys and integer list indices, for example:

- `svg.entities.reactor.label`
- `svg.edges.feed_to_pump.from`
- `svg.edges.feed_to_pump.marker_end`
- `svg.chart_values.Measurement|Run A.value`
- `csv.measurements.csv.values.Measurement|Run A.value`
- `svg.layer_set`
- `svg.text_count`

Supported operators are `eq`, `neq`, `exists`, `contains`, `includes_all`, `set_eq`, `lt`,
`lte`, `gt`, `gte`, and `approx`. `exists` expects no `expected` value; all others do.
`approx` uses optional absolute `tolerance` (default `1e-9`). Missing paths and type errors
fail; they never count as N/A.
