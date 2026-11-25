# Tiling and reading protocol

The supply chain delivers three levels of pixels: panel crops (`panels.json`),
zoom tiles (`zoom_manifest.json`), and the original image. **Read from tiles,
never from the full-page view.** This file says which tile answers which
question and how to keep coordinates traceable.

## Which tile answers which question

| question | tile to read | notes |
|---|---|---|
| Axis type (linear vs log) | `panel_N_left_axis.png` | on a log axis, major ticks are spaced by decade with compressed minor ticks (2–9) between them; check whether labels step ×10 (log) or by equal increments (linear) |
| Y tick values / unit prefix (m vs µ vs k) | `panel_N_left_axis.png` | prefixes sit inside tick labels ("µM", "mV"); at 4× zoom they are legible where the page view blurs them |
| X tick values | `panel_N_bottom_axis.png` | rotated x labels are common; read each label fully |
| Axis titles / units | `panel_N_left_axis.png` (y title, vertical text) and `panel_N_bottom_axis.png` (x title) | the title strip may also carry the axis title if it sits above the panel |
| Series names / legend symbols | `panel_N_legend_zone.png` | top-right quadrant at 3×; if the legend is elsewhere, request an extra crop of that quadrant from the panel crop |
| Panel label (a)/(b)/A/B | `panel_N_title_strip.png` plus `label_guess` in `panels.json` | the guess is a heuristic cluster location; verify against the pixels |
| Panel-level layout, curve identity | `panel_N.png` (the 2× panel crop) | use only to *locate* content; read values from the zoom tiles |

## Converting tile pixels back to original-image coordinates

Every tile entry in `zoom_manifest.json` carries:

```
bbox_original = [x0, y0, x1, y1]   # rectangle in the ORIGINAL image
scale         = s                  # tile px per original px
```

A pixel observed at `(tx, ty)` inside the tile maps to the original image as:

```
orig_x = x0 + tx / s
orig_y = y0 + ty / s
```

The same rule applies to panel crops using `bbox_original` and `scale` from
`panels.json`. Distances convert by dividing by `s`. Because every reading
must be citable, keep the tile name and this bbox next to every value you
write into `result.json`'s `sources`.

## Reportability rule

A value is **reportable only with its source tile recorded**. Concretely,
each entry in `sources` should look like:

```
{"claim": "y-axis unit", "value": "mV",
 "tile": "panel_1_left_axis.png",
 "bbox_original": [10, 55, 95, 505]}
```

If you read something from the panel crop rather than a zoom tile (acceptable
for locating, risky for values), record the panel crop and its bbox the same
way — and prefer re-checking the value in the corresponding zoom tile.

## Reading order inside a panel

1. `title_strip` — confirm panel label and any panel-local title.
2. `left_axis` — y axis type, tick values, unit prefix, axis title.
3. `bottom_axis` — x axis ticks and title.
4. `legend_zone` — series names; map symbols/colors to names.
5. `panel_N.png` — spatial context only (which curve sits where).

## When tiles are not enough

- If a needed region (e.g. a legend in the bottom-left) is not covered by the
  standard tiles, crop it yourself from the panel crop with PIL, record the
  new bbox in original coordinates (panel `bbox_original` + offset / panel
  `scale`), and treat it as an ad-hoc tile with the same provenance rule.
- If even the zoom tile is illegible, do **not** guess: mark the field
  partial, cite the tile, and state the legibility limit in `uncertainty`.
