# element_ledger.json — the g3 artifact

The ledger is the coverage guarantee (提得全): every element of the
figure that could carry a number is explicitly accounted for, either read
with a locator, declared not present, or declared unreadable with a
reason. Elements that fall through the cracks are the number-one cause of
"partial credit" reviews.

```json
{
  "legend_entries": 2,
  "entries": [
    {
      "element_type": "series",
      "id": "WT dose-response",
      "status": "read",
      "locator": "fig_2b.png#axes(60,15)-(620,470)#x[0.05,100]#y[2,98]",
      "value": "8 points, y ±1.0%"
    },
    {
      "element_type": "errorbar",
      "id": "WT point 4 error bar",
      "status": "read",
      "locator": "fig_2b.png#x[9.5,10.5]#y[70,80]",
      "value": "±3.1%, semantics SD (caption: 'mean ± SD, n=5')"
    },
    {
      "element_type": "significance_mark",
      "id": "bracket above KO/WT at high dose",
      "status": "read",
      "locator": "fig_2b.png#x[2.5,3.5]#y[88,96]",
      "value": "***"
    },
    {
      "element_type": "scale_bar",
      "id": "SEM inset scale bar",
      "status": "unreadable",
      "locator": "fig_2c.png#inset(x:500-600,y:300-340)",
      "reason": "scale bar label overexposed in the provided raster; the
                 inset's text is not legible at this resolution"
    }
  ]
}
```

## Rules enforced by gate.py

- `element_type` ∈ series | data_point | errorbar | significance_mark |
  scale_bar | annotation | legend | axis | subfigure_label
- `status` ∈ read | not_present | unreadable
- `read` requires `locator` — a figure region (`file#box`), a table cell
  (`file#row-n#col-name`) or a caption quote (`caption: "…"`).
- `unreadable` requires `reason` — a specific statement a reviewer can
  act on, not "hard".
- If `legend_entries` is set (count the legend items), the number of
  `series` entries marked read must be ≥ that count.

## Element-specific discipline

- **errorbar** — record the semantics (SD/SEM/CI/range/min-max) with a
  caption quote; pixels alone cannot distinguish SD from SEM.
- **significance_mark** — decode the symbol (*/**/***/ns), name what is
  being compared, and carry the caption's definition ("*P < 0.05,
  two-sided t-test").
- **scale_bar** (micrographs) — record the labeled real-world length;
  measurements derived from it must carry the conversion you used.
- **annotation** — in-figure text that changes meaning ("pre-dose",
  "break", "normalized to day 0"). Axis-break marks are annotations too
  — a broken axis changes how values must be read.
- **not_present** is a finding, not a failure: a figure with no error
  bars should say so, so the reviewer knows you checked.
