# axis_card.json — the g2 artifact

One card per panel. Fill it while zoomed into the figure; gate.py checks
it mechanically before any value is read.

```json
{
  "panel": "b",
  "axes": [
    {
      "name": "x",
      "label": "dose (uM)",
      "unit": "uM",
      "type": "log",
      "ticks": [
        {"value": 0.1, "px": 96},
        {"value": 1.0, "px": 227},
        {"value": 10.0, "px": 358},
        {"value": 100.0, "px": 489}
      ],
      "plot_area": [60, 15, 620, 470]
    },
    {
      "name": "y",
      "label": "response (%)",
      "unit": "%",
      "type": "linear",
      "ticks": [
        {"value": 0, "px": 462},
        {"value": 20, "px": 374},
        {"value": 40, "px": 286},
        {"value": 60, "px": 198}
      ],
      "plot_area": [60, 15, 620, 470]
    }
  ]
}
```

## Field rules

- `label` — axis title copied **verbatim**, including its unit in the
  original form. Read it character by character: `mV` ≠ `V`, `µm` ≠ `nm`,
  `µ` ≠ `u`.
- `unit` — the unit alone, verbatim characters. For genuinely unitless
  axes set `"unit": null` and `"dimensionless": true` (gate warns
  otherwise).
- `type` — decided by the tick **labels**, not by how the figure looks:
  constant difference between successive labels → `linear`; constant
  ratio (1, 10, 100 or 2, 4, 8) → `log`. gate.py recomputes this from
  your tick pixels and values and fails the card on disagreement.
- `ticks` — ≥3 entries `{value, px}`; `px` is the pixel coordinate along
  the axis in the image (origin top-left; y pixels grow downward — list
  ticks in increasing pixel order). Tick pixels must be strictly
  monotonic.
- `plot_area` — `[left, top, right, bottom]` of the data rectangle in
  pixels, with left < right and top < bottom.

## Reading geometry

- Linear calibration: value = a·px + b from a least-squares fit over your
  ticks; keep the max residual as your per-axis reading error.
- Log calibration: log10(value) = a·px + b. A "linear" fit on a log axis
  is the single most expensive misread — g2 exists to catch it.
- Reciprocal or inverted axes (values decreasing with pixel): declare
  `"inverted": true` and keep ticks in increasing-pixel order; gate
  checks monotonicity of pixels and values in their own orders.
