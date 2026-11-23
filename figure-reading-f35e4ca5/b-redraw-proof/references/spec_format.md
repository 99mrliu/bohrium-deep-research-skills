# figure_spec.json format

The spec is the complete, self-contained declaration of what the agent
read from the figure. `to_spec.py` validates it; `replot.py` renders only
from it. Everything that will appear in the reconstruction must be here.

## Skeleton

```json
{
  "figure": {"title": "optional verbatim title", "width_in": 5.0, "height_in": 3.5},
  "axes": {
    "x": {"label": "dose (uM)", "unit": "uM", "type": "log", "range": [0.05, 100]},
    "y": {"label": "response (%)", "unit": "%", "type": "linear", "range": [0, 100]}
  },
  "series": [
    {"name": "WT", "kind": "line", "marker": "o", "color": "#0072B2",
     "points": [[0.1, 5.1], [1.0, 25.8], [10.0, 75.1]]},
    {"name": "KO", "kind": "scatter", "marker": "s", "color": "#D55E00",
     "points": [[0.1, 2.8], [1.0, 8.8], [10.0, 35.9]]},
    {"name": "viability", "kind": "bar", "color": "#009E73",
     "categories": ["ctrl", "drug"], "values": [100.0, 42.0],
     "errors": [4.0, 5.0], "error_semantics": "SD"}
  ],
  "annotations": [{"text": "n=5", "x": 1.0, "y": 30.0}]
}
```

## Field rules

- `axes.*.label` — the axis title **copied verbatim** from the figure,
  including the unit in its original parentheses. `unit` repeats just the
  unit string; `replot.py` appends it only if absent from the label.
- `axes.*.type` — `linear` or `log`. Decide by tick *labels*: constant
  difference → linear; constant ratio (powers of ten) → log.
- `axes.*.range` — the axis limits **as read from the tick extremes**,
  not padded guesses.
- `series[].name` — the legend entry verbatim; if the figure has no
  legend, name the series by its caption role (`"control"` etc.) and say
  so in the answer.
- `kind` — `line` | `scatter` | `bar`. A bar series uses
  `categories`/`values` (+ optional `errors`, `error_semantics` one of
  SD/SEM/CI95/range/unknown — read it from the caption, never guess).
- `color` — `#rrggbb` sampled from the figure ink, or a basic color name.
  Colors enable per-series recall in `overlay_diff.py`.
- `points` — data coordinates (not pixels) in axis order.
- `annotations` — in-figure text that carries meaning (n, significance
  stars decoded, scale notes). Pure decoration is omitted.

## Reading discipline before writing the spec

1. Zoom/crop the figure (PIL crop, or `pdftoppm -png -r 300` for a
   PDF-embedded figure). Read tick labels digit by digit.
2. For log axes, read the *decade labels*, not the minor ticks.
3. Read points against the calibrated axes (tick pixels → linear/log
   transform); a spec point is a *data coordinate*, never a pixel.
4. Record what cannot be read (occluded points, ambiguous legend mapping)
   in the result's `uncertainty`, not as invented spec entries.
5. Multi-panel figures: one spec **per panel**; render and diff each
   separately.
