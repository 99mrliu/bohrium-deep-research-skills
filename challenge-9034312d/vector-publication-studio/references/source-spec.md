# Source specification and chart mapping

## Top level

`spec_version`, `synthetic`, `title`, `subtitle`, `description`, `canvas`, `diagram`, `nodes`, `edges`, `charts`, `sources`, `footer`, and `change_records`. Actual cases must set `synthetic` to false and replace all example values.

Canvas `width`/`height` are viewBox units. `physical_width`/`physical_height` are millimetres written to the SVG root. Diagram `x/y/width/height` delimit the apparatus panel. Chart panel boxes are explicit to keep multi-panel publication layouts stable.

## Nodes

Required: `id`, `label`. Optional: `kind` (default `process`), `rank`, `lane`, `width`, `height`, `font_size`, `max_label_lines`, `sublabel`, and `sources`.

Glyphs are `reservoir`, `pump`, `reactor`, `sensor`, `detector`, `column`, `cell`, `valve`, `sample`, `process`, and `output`. They are schematic visual roles, not new scientific assertions. Choose only the role supported by the source; use `process` when uncertain.

If all ranks are omitted, ranks derive from process/material edges. Information feedback is not used for ranking. If a process cycle prevents topological ordering, add explicit ranks and identify feedback honestly. Lanes are integer rows. One rank/lane slot cannot contain two nodes. Labels wrap by measured approximate Latin/CJK text units; excessive lines fail rather than clip.

For traceability, each node should carry `sources`: source IDs or objects containing `source_id`, `locator`, and `support`. The actual-paper runner reports missing node sources as an honest partial.

## Edges

Required: unique `id`, valid `from`, valid `to`. Optional: `kind`, short `label`, `sources`. Self-loops must be split into explicit stages.

| kind | color | redundant line/marker | meaning |
|---|---|---|---|
| `material` / `flow` | blue `#0072B2` | solid, arrow | material/fluid direction |
| `energy` | orange `#D55E00` | dashed, arrow | energy direction |
| `information` | purple `#6A51A3` | dotted, arrow | signal/information direction |
| `activation` | green `#15803D` | solid, arrowhead | activating/enabling relation |
| `inhibition` | red `#B91C1C` | solid, perpendicular terminal bar | inhibiting/blocking relation |

Do not use activation and inhibition as interchangeable arrow styles. Do not use color alone. The legend derives from kinds actually used. An edge label must reflect the source; the default legend phrase is not evidence of a relation.

The router uses direction-aware Dijkstra search on an orthogonal coordinate grid, avoids node rectangles, penalizes bends, reserves upper/lower feedback channels, and fails if it cannot find a route. Output vertices appear in `layout_manifest.json`. Inspect for accidental visual junctions; adjust lanes when necessary.

## Charts

Each chart requires:

- `data_csv`: path relative to the source spec;
- `x_column`: exact header in the CSV;
- `y_columns`: nonempty list of `{column, label}` objects;
- `x_label`, `y_label`: include actual units;
- optional `x_min`, `x_max`, `y_min`, `y_max`, `box`, `title`, and `id`.

The builder opens the real CSV, checks headers and every selected cell, rejects missing/nonfinite/nonnumeric values, requires at least two rows, sorts by numeric x, rejects duplicate x values, and derives ranges from actual values unless explicit valid ranges are supplied. No silent interpolation, aggregation, unit conversion, or fabricated replacement occurs. Series color and dash are redundant, every point has a native SVG `<title>` carrying x and y values, and the series legend derives from mapped columns. Copied CSV(s) and mappings are recorded beside the SVG.

The current chart primitive is a multi-series line/scatter chart for a shared numeric y unit. For a categorical/bar task, transform the requested data into a suitable separate editable SVG only if the semantics remain explicit, or extend this source spec with a tested bar primitive; never substitute unrelated numeric values or claim the line chart is a bar chart. All chart tasks remain in scope and missing/incompatible data must be reported rather than ignored.

## Sources and changes

Use page/panel/caption/method/CSV row-column locators. Layout decisions are not scientific evidence. A `change_records` entry should state whether the action was a new build or a source-preserving patch, exact addressed IDs if applicable, source reason, and confirmation/uncertainty status.
