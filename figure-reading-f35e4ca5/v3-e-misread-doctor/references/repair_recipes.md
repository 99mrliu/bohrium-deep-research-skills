# Repair cookbook — worked recipes 修复手册

Full repairs with numeric mini-examples. Mode ids match
`references/failure_taxonomy.md` and the recipe table inside
`scripts/repair_plan.py`. Rules for wording repairs inside `result.json` are at the
bottom.

---

## LOG_AXIS_AS_LINEAR — convert pixels through the log law

Detector output gives `log: {a, b}` for `pixel = a·log10(value) + b`.

**Worked example.** y-axis ticks measured on the image:

| tick value | pixel y |
|---|---|
| 1e-3 | 620.0 |
| 1e-1 | 430.0 |
| 1e1  | 240.0 |

Fit: two decades span 190 px → `a = -95.0` (pixel decreases as value grows),
`b = 335.0`. A data point at pixel y = 382.0:

```
value = 10**((382.0 - 335.0) / -95.0) = 10**(-0.4947) ≈ 0.320
```

The misread: linear interpolation between the 1e-1 (430 px) and 1e1 (240 px) ticks
gives 0.1 + (430−382)/(430−240)·(10−0.1) ≈ **2.60** — an 8× error. Always convert
through the log law; when reporting ranges on a log axis, quote *ratios/decades*,
never pixel averages.

## LINEAR_AXIS_AS_LOG / SYMLOG_SUSPECT

- Linear-in-disguise: refit `pixel = a·value + b` and re-read; a log-law "reading"
  of evenly spaced values compresses the high end — e.g. true 80 read as
  `10**(log10(20) + 0.75·(log10(100)−log10(20)))` ≈ 33.7.
- Symlog: split at 0. With ticks −100, −10, −1, 0, 1, 10, 100 evenly spaced, a point
  midway between the 1 and 10 ticks is `10**0.5 ≈ 3.16`, but a point midway between
  0 and 1 is ≈ 0.5 (linear region). State the linthresh you assumed.

## UNIT_PREFIX — normalize once, explicitly

**Worked example.** Axis `Potential (mV)`, table column `potential_V`,
contract expects volts. Raw read: 320 (mV). Conversion factor from
axis_diagnosis.json: `axis_to_table = 1e-3`.

```
reported = 320 mV × 1e-3 = 0.320 V
```

Prefix table the detector normalizes: `m`=1e-3, `µ/u/μ`=1e-6, `k`=1e3, `M`=1e6,
plus `×10^n` axis notations (an axis labelled "×10³" multiplies every tick label).
Common traps: `ms` vs `s` (1e-3), `kHz` vs `Hz` (1e3), `µM` vs `mM` (1e-3 — both
prefixed!). Apply the factor ONCE, at read time, never per-field by memory.

## PERCENT_FRACTION

Axis 0–100 (%), contract fraction: divide by 100 once. Axis fraction, contract
percent: multiply by 100. `‰` divides by 1000. State which form result.json carries
("value 0.35 = fraction form of the figure's 35%").

## DUAL_AXIS — bind before reading

**Worked example.** Left axis "Temperature (°C)", 0–50; right axis "Rainfall (mm)",
0–200. Legend: blue line = temperature, bars = rainfall. A blue-line point at pixel
y that is 60% up the panel:

- against the LEFT axis: 0.60·50 = **30 °C** ✔
- against the RIGHT axis: 0.60·200 = **120 mm** ✘ (the classic 4× misread)

Write the binding into `sources`: `"series_binding": {"blue line -> left y (°C),
bars -> right y (mm), verified on zoomed legend swatches"}`.

## TRUNCATED_ORIGIN — quantify the distortion

**Worked example.** Bar chart, y from 40 to 110 (truncated). Bars: Control 55,
Treatment 60.

- Value ratio: 60/55 ≈ **1.09** — the honest finding.
- Pixel-height ratio: heights are (55−40)=15 and (60−40)=20 units → 20/15 ≈
  **1.33** — what the eye reports. 22% exaggeration of the *relative* difference.
- Detector metrics: visible fraction = (110−40)/(110−0) = 0.636; zero-baseline
  exaggeration ratio = 110/70 ≈ 1.57.

Report: "Treatment 60 vs Control 55 (ratio 1.09). Note: the y-axis starts at 40, so
bar heights exaggerate the difference (height ratio 1.33)." Never write "Treatment
is 33% higher" from the heights.

## CROPPED_AXIS

Readable range is the tick range, not the data range. If the curve exits the panel
at y = 110 (top tick), report `"> 110 (cropped)"` in the value or mark the field as
a gap: `"value": null, "gap": "curve exceeds cropped axis range >110"`. Never
extend the axis by extrapolating tick spacing.

## NONDATA_STAR / NONDATA_BRACKET

Stars and brackets are *claims about* the data. Record them as annotations:

```
"significance": [{"groups": ["Control", "Treatment"], "stars": "**",
                  "bracket_bbox": [...]}]
```

and exclude their pixels from every digitized series. Check digitized points against
candidate bboxes from nondata_elements.json before filling result.json.

## FIT_LINE

A fit line is a model overlay. If the task asks for the trend: read two points ON
the line, compute slope, report as `"slope_fit": ..., "note": "linear fit overlay,
not data"`. If not asked: exclude entirely.

## INSET_AXIS / LEGEND_SWAP

- Inset: calibrate separately (own tick fit), read within the inset frame only; a
  zoom inset wins over the main panel for fine structure in its range.
- Legend swap: anchor name→color/marker at the legend swatch on a zoomed crop;
  write the binding into `sources`.

---

## Reporting repairs inside result.json

- **sources**: one entry per applied repair, locatable and specific:
  `"unit conversion mV→V ×1e-3 applied to top-panel reads (axis_diagnosis.json
  flag UNIT_PREFIX, axis top_y)"`, `"series binding blue→left axis verified on
  legend zoom"`, `"star/bracket annotations excluded from data
  (nondata_elements.json candidates #1–#3)"`.
- **uncertainty**: residual doubt, quantified when possible:
  `"log-axis reads accurate to ±0.5 minor-tick spacing ≈ ±8% of value"`,
  `"declared-vs-geometry conflict on bottom x unresolved — values provisional"`.
- **status**: `success` only when every contract field is filled, every claim
  locatable, and every `agent_confirm` item resolved; otherwise `partial` with
  explicit `limits`. A detector that fired but was dismissed on visual inspection
  still gets one line in `misread_report.json` (`applied: false` + why).
- **gaps**: figures mentioned but not shipped are listed as gaps, never
  reconstructed; cropped-out values are gaps, never extrapolations.
