# figure_plan.json reference

One JSON file fully describes the figure. `draw_figure.py` renders it;
`readback_verify.py` re-reads the rendered SVG and checks it against this
plan (and through it, against the source data). Keep the plan SMALL and
grounded: every number must come from a source you read.

## Top-level fields

| field | type | default | meaning |
|---|---|---|---|
| `title` | string | "" | figure title (chart: not drawn per-panel unless panel.title set; diagram: drawn) |
| `mode` | "chart" \| "diagram" | "chart" | diagram = mechanism/flow schematic |
| `width_mm` | number | 89 (chart) / 120 (diagram) | 89 mm ≈ single column, 174–183 mm double column |
| `height_mm` | number | 70 / 80 | figure height |
| `style` | "default_pub" \| "grayscale" | "default_pub" | see presets below |
| `png_dpi` | int | 300 | PNG export resolution |
| `panels` | list | [{}] | 1 panel = single plot; >1 = 1×N subplot row |
| `diagram` | object | – | required in diagram mode |
| `verify` | object | {} | `{"tol_rel": 0.02, "tol_abs": 1e-9}` overrides |

## Chart panels

```json
{
  "id": "p0",
  "type": "bar | line | scatter",
  "categories": ["Ctrl", "Drug"],            // bar charts (required)
  "x": [0, 1, 2],                            // shared numeric x (line/scatter)
  "series": [ ... ],
  "x_label": "Time", "x_unit": "h",
  "y_label": "Signal", "y_unit": "a.u.",
  "title": "optional panel title",
  "legend": true
}
```

- Units: put the unit in `x_unit`/`y_unit`, the quantity in `x_label`/
  `y_label`. The drawer renders `"Signal (a.u.)"`; the verifier checks the
  label text AND the unit string appear. Never bake units into values
  silently — if the source is in `%` and you plot fractions, say so in
  `source_locator` and `uncertainty`.
- Magnitude: plot values in the source's own magnitude. If you rescale
  (e.g. ÷1000), record it in the series' `source_locator` note and keep
  the axis label honest.

### Series

```json
{
  "name": "WT",                              // appears in legend; keep short
  "values": {"file": "/app/work/data.csv", "column": "WT_mean"},
  "yerr":   {"file": "/app/work/data.csv", "column": "WT_sd"},   // bar only
  "x":      [0, 1, 2],                        // per-series x override
  "color":  "#0072B2",                        // optional; default = palette
  "marker": "o",                              // line only; default auto
  "source_locator": "data.csv#WT_mean rows 1-5, table S2 of paper.pdf#page4"
}
```

Binding rules:

1. **Prefer file bindings** (`{"file": ..., "column": ...}`) for anything
   from a data file — the drawer and the verifier both re-read the same
   file, so a wrong column is caught mechanically. CSV/TSV (delimiter
   sniffed) and JSON (list-of-dicts or dict-of-lists) are supported.
   Relative paths resolve against the plan file's directory.
2. **Literal lists** are for values extracted from a paper (e.g. read off
   a table in the PDF). Then `source_locator` is MANDATORY and must say
   where each value came from (`paper.pdf#page3#table2 row "WT"`).
3. Lengths must match: bar `values` == `categories`; line/scatter
   `x` == `values`; `yerr` == `values`. Mismatch → clean exit-2 error.
4. NaN / empty cells: omitted from the drawing with a `nan_gap` warning;
   the verifier treats them as expected gaps. Do NOT silently replace
   NaN with 0 — that fabricates data.

### Chart-type selection

- `bar`: categorical x, compare magnitudes; use `yerr` when the source
  reports SD/SEM (label which one in the plan notes/result.json!).
- `line`: ordered numeric x (time, dose, wavelength); markers auto when
  ≤30 points.
- `scatter`: unconnected paired measurements, correlations.
- Multi-panel: list several panels; keep panel count ≤ 4 and width ≤
  183 mm total. Each panel gets its own gid scope (`p0`, `p1`, …).

### Style presets

- `default_pub`: colorblind-safe palette `#0072B2 #E69F00 #009E73
  #CC79A7 #56B4E9 #D55E00 #F0E442 #000000` (Okabe-Ito), 7.5 pt base
  font, 1.0 pt lines, top/right spines off, tight bbox.
- `grayscale`: gray palette + black bar edges, for print-only venues.

## Diagram mode (mechanism / flow figures, figure03-type)

```json
{
  "mode": "diagram", "width_mm": 120, "height_mm": 80,
  "diagram": {
    "nodes": [
      {"id": "egfr", "label": "EGFR", "shape": "box",
       "x": 30, "y": 20, "w": 18, "h": 10, "color": "#E8F1F8", "wrap": 0}
    ],
    "edges": [
      {"from": "egfr", "to": "ras", "style": "->", "label": "activates"}
    ]
  }
}
```

- Coordinates: 0–100 space, **origin top-left, y grows downward** (like
  slide coordinates). `x,y` = node center; `w,h` = node size.
- Shapes: `roundbox` (default), `box`, `circle`, `diamond`, `cylinder`
  (databases/stores).
- Edge styles: `->` (activation/flow), `-[` (inhibition, bar-headed),
  `--` (dashed arrow), `line` (plain).
- `wrap`: chars per line for the label; default auto from `w`; 0 disables.
- **Spelling is a scoring dimension.** Copy every entity name
  character-for-character from the paper (gene symbols, protein names,
  capitalization, hyphens, Greek letters). The verifier fails the figure
  if any label is missing or differs.
- Layout rules of thumb: main pathway left→right or top→bottom; inhibitory
  edges visually distinct (`-[`); keep ≥ 8 units between node edges;
  use `references`-grounded arrow semantics (an arrow must mean something
  the source supports).

## Worked micro-plan

See `examples/minimal_example.md` for a complete run including a
deliberately corrupted plan that the verifier catches.
