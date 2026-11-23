# figure_spec.json grammar (Bundle A)

Top level:

```json
{
  "case_id": "copied from case.json",
  "title": "figure headline (numbers in it must be anchored like everything else)",
  "title_pt": 12,
  "canvas": {"width_in": 7.2, "height_in": 4.0, "dpi": 300},
  "reading_order": ["a", "b"],
  "panels": [ ... ],
  "exceptions": [{"id": "ex-1", "finding": "exact issue text from check_spec",
                  "reason": "why this is acceptable"}]
}
```

## Schematic panel

```json
{"id": "a", "kind": "schematic", "title": "Mechanism", "title_pt": 10,
 "rect_in": [0.15, 0.45, 3.9, 2.5],
 "nodes": [
   {"id": "drug", "label": "Staurosporine\n5 uM, 6 h", "sublabel": "",
    "role": "intervention", "xywh_frac": [0.02, 0.30, 0.26, 0.30],
    "font_pt": 8, "fill": "vermillion", "edge": "black",
    "text_color": "#000000",
    "source": {"locator": "paper page 2, Methods", "quote": "verbatim"}}
 ],
 "edges": [
   {"from": "drug", "to": "cells", "label": "", "style": "arrow",
    "color": "black", "font_pt": 8,
    "source": {"locator": "...", "quote": "..."}}
 ],
 "annotations": [
   {"text": "n = 3", "xy_frac": [0.02, 0.05], "font_pt": 8, "italic": true,
    "source": {"locator": "...", "quote": "..."}}
 ]}
```

- `rect_in`: [x, y, w, h] in **inches**, top-left origin, must fit the canvas.
- `xywh_frac`: [x, y, w, h] in **panel-fraction** coordinates (0–1),
  top-left origin. The gate rejects overlaps > 0.01 in both axes and labels
  that do not fit their box (Helvetica width estimate).
- `role`: `entity | process | outcome | condition | intervention | note`
  (drives fill colour from the Okabe-Ito colour-blind-safe set).
- `fill` may be a safe token name or `#rrggbb`; anything else is a finding.
- Edge `style`: `arrow | inhibit | dashed | plain`. Unlabelled edges still
  need a source if the relation itself is a factual claim (it usually is).

## Chart panel

```json
{"id": "b", "kind": "bar", "title": "Cell viability (CCK-8)",
 "rect_in": [4.35, 0.45, 2.7, 2.5],
 "x_label": "Condition", "y_label": "Viability (%)", "legend": true,
 "series": [
   {"name": "viability", "x": [0, 1], "y": [100, 42],
    "x_labels": ["control", "staurosporine 5 uM"],
    "yerr": [0, 3.1], "color": "blue",
    "source": {"locator": "viability.csv", "quote": "verbatim sentence or header",
               "data_ref": {"file": "viability.csv"}}}
 ]}
```

- `kind`: `bar | line | scatter`. `y` values are checked against the quote
  and/or the `data_ref` file content — they must be literally present
  (commas ignored). `yerr` values are checked the same way.
- Multi-series charts require `legend: true` (default).
- Axis labels with units are required whenever the source shows units.

## What the gate enforces (summary)

| ID | Rule | Severity |
|----|------|----------|
| S1 | required fields, unique ids, edge endpoints exist | blocker |
| S2 | factual elements carry verbatim `quote` + `locator` present in pool | blocker |
| S3 | every number in labels/series found in its quote or `data_ref` | blocker |
| S4 | panels in canvas, nodes in panel, no overlaps, label fits box | blocker |
| S5 | colours are safe tokens or valid hex visible on white | blocker |
| S6 | chart axes labelled; multi-series charts have legends | blocker |

All blockers; disposition only via `exceptions` with the exact issue text.
