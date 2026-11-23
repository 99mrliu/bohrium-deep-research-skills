# Workorder schema (v1)

A **workorder** is a JSON file `{"ops": [op, ...]}`. Ops are applied **in
order** by `scripts/apply_workorder.py`. Geometry-affecting ops re-derive
pixels from the bound source values through `figmap.json` — you declare the
intent in *data* units, the engine computes pixels. Never hand-compute pixel
coordinates into a workorder.

Every op produces one change-log entry:
`{seq, ts, op, op_args, target, old, new, source_ref, manual_reason, status,
detail}` with `status ∈ {applied, rejected, failed}`. Unknown targets →
`failed` (the remaining ops still run). The engine exits 2 if ops were
attempted but none applied.

## Provenance discipline (read first)

- `source_ref` forms:
  - `"data.csv#column=rate,row=4"` — a cell in a source data file
  - `"data.csv#column=rate"` — a whole column
  - `"paper.pdf#page=3,fig2"` — a value read from the paper
  - any `"<file>#<locator>"` string that lets a reviewer find the number
- **Value-changing ops** (`update_value`) without `source_ref` are
  **REJECTED** unless the op carries `"manual": true` and `"reason": "..."`.
  Manual edits are then applied but logged conspicuously as 人工修改.
- `add_annotation` without `source_ref`/`manual` is applied but flagged with a
  warning in `detail`.
- Style/label/move ops (`restyle_series`, `relabel`, `move_annotation`,
  `highlight_region`) carry no value burden; they are still logged with
  old/new.

## Ops

### update_value — change one bound datum
```json
{"op": "update_value", "series": "drug", "key": "B", "value": 3.6,
 "source_ref": "data.csv#column=drug,row=B"}
```
- `series` (required): series name from the compose plan / figmap.
- `key` (category x) **or** `index` (0-based) — which point.
- `value` (required): new y value. Optional `x`: new x (linear axes only).
- Geometry rewritten: bar rectangle, line vertex (+ its marker glyph), or
  scatter point. The figmap's stored values are updated so later ops see them.
- Known limit: `yerr` (error-bar) geometry is **not** re-derived; the log
  entry carries a warning — verify error bars visually or re-compose.

### restyle_series — color / linestyle of a whole series
```json
{"op": "restyle_series", "series": "ctrl", "color": "#009E73",
 "linestyle": "--"}
```
- `color`: hex; applied to whichever of fill/stroke the glyphs actually use
  (bars→fill, lines→stroke, scatter→both).
- `linestyle`: `"-"`, `"--"`, `":"`, `"-."` or a raw dash array `"6,3"`.
- `marker`: accepted but **not** applied to scatter glyphs (marker shapes live
  in `<defs>`); a warning is logged.

### relabel — replace text content
```json
{"op": "relabel", "target_id": "label/title", "new_text": "新标题"}
```
- `target_id` may be a `<text>` element or a group containing one (first text
  descendant is replaced). Old text is recorded.
- Standard ids from the composer: `label/title`, `label/x`, `label/y`;
  tick labels live in groups `xtick_N` / `ytick_N`.

### move_annotation — translate an element/group
```json
{"op": "move_annotation", "target_id": "annotation/sig1", "dx": 5, "dy": -3}
```
- `dx`, `dy` in SVG user units (px; +y is DOWN). Works on text (x/y attrs),
  `<use>`, and groups (appended `translate(...)`).

### add_annotation — new label + leader line at a data coordinate
```json
{"op": "add_annotation", "id": "sig1", "x_data": "B", "y_data": 3.6,
 "text": "p<0.05", "source_ref": "paper.pdf#page=3,fig2"}
```
- `x_data` accepts a category name or numeric x (linear axes); placed through
  the figmap. Optional `leader_dx`/`leader_dy` (default 10/-14 px) control the
  leader-line length. Creates group `annotation/<id>`.

### set_axis_range — re-fit an axis and rescale ALL bound glyphs
```json
{"op": "set_axis_range", "axis": "y", "min": 0, "max": 4}
```
- Linear axes only. Re-fits the figmap transform, rewrites every bound glyph
  from stored values, and rewrites the existing tick groups (same count,
  evenly spaced new values, labels formatted `%g`).
- `axis:"x"` on a categorical axis → `failed`. Bar charts on linear x: x
  rescale unsupported → `failed`.

### highlight_region — background band behind the data
```json
{"op": "highlight_region", "x0": "B", "x1": "C", "label": "treated"}
```
- Inserts a translucent rect as the first child of the axes group (behind all
  series), spanning the full plot height, `x0..x1` mapped through the figmap.

## figmap.json (the binding sidecar)

Written by `compose_svg.py`; read and re-written by the engine.

```json
{"figmap_version": "1.0", "calibrated": true,
 "canvas": {"width_px": ..., "height_px": ...},
 "plot_area": {"x_left_px": ..., "x_right_px": ...,
               "y_top_px": ..., "y_bottom_px": ...},
 "baseline_y_px": ...,
 "axes": {"x": {"kind": "category", "categories": [...],
                "centers": {"A": px, ...}, "step_px": ...}
              | {"kind": "linear", "a": ..., "b": ..., "min": ..., "max": ...},
          "y": {"kind": "linear", "a": ..., "b": ..., "min": ..., "max": ...}},
 "series": {"<name>": {"kind": "bar|line|scatter", "element_ids": [...],
                       "x": [...], "y": [...], "yerr": [...]|null,
                       "baseline": 0.0, "source": ..., "source_locator": ...}}}
```
`svg_px = a * value + b`, fitted from the *actual* written geometry
(`calibrated: true`); if calibration failed the transform is predicted and a
warning is recorded — treat geometry edits cautiously then.

**No figmap (e.g. a layerized external figure)** → value ops fail as
`unbound - manual confirmation required`; style/label/move ops still work.
