# Failure taxonomy — 12 named misread modes 误读模式分类

Each mode: id, name (EN + 中文), fingerprint, why base agents fall for it, detector
logic, repair, and the post-read self-check question. The figure_card.json schema is
at the bottom — the card is what makes the cheap detectors possible.

Pixel coordinates everywhere follow the image convention: origin **top-left**,
y **down**. A tick's `pixel` is the coordinate *along* its own axis (y-pixel for a
y axis, x-pixel for an x axis).

---

## 1. LOG_AXIS_AS_LINEAR — 对数轴误判为线性轴

- **Fingerprint**: tick labels read 0.001, 0.01, 0.1, 1, 10 (equal pixel spacing,
  ×10 steps), but the agent assumed linear — or the axis title omits "log".
- **Why agents fall**: VLM-style reading latches onto label *text* and interpolates
  pixel positions linearly; a point midway between the 1 and 10 ticks is read as
  ~5.5 instead of √10 ≈ 3.16. Differences at the bottom of the axis are silently
  compressed, ratios at the top inflated.
- **Detector**: least-squares fit of tick (value → pixel) under two models,
  `pixel = a·value + b` and `pixel = a·log10(value) + b`; if the log residual is
  small *and* < 30% of the linear residual while the card declared `linear`, fire.
- **Repair**: convert via `value = 10**((pixel − b)/a)` with fitted a, b; report in
  the original unit but think in decades; never average raw pixel positions.
- **Self-check**: does `10**((pixel−b)/a)` reproduce a tick-anchored value you can
  verify by eye? Quote both numbers.

## 2. LINEAR_AXIS_AS_LOG — 线性轴误判为对数轴

- **Fingerprint**: axis believed log (caption said "log scale", or the *other* axis
  is log) but ticks are evenly spaced in value.
- **Why agents fall**: semilog/loglog plots prime a "log" prior that spills onto
  every axis of the figure.
- **Detector**: same two fits as mode 1, opposite conclusion vs declared `log`.
- **Repair**: re-fit linear, re-read every value from that axis, state the
  correction in `uncertainty`.
- **Self-check**: do three evenly spaced tick labels differ by equal additions, not
  equal ratios? Quote the three labels.

## 3. SYMLOG_SUSPECT — 对称对数轴嫌疑

- **Fingerprint**: ticks cross zero with labels like −100, −10, −1, 0, 1, 10, 100;
  spacing is log-like in |value| but linear near zero.
- **Why agents fall**: it looks like a broken log axis; agents either panic or apply
  a pure log law and produce nonsense near zero.
- **Detector**: ticks span zero; probe fit of `pixel = a·sign(v)·log10(1+|v|) + b`
  beats the plain linear fit.
- **Repair**: split reading at 0; each side follows its own signed-log law; values
  inside the linthresh band are effectively linear — say so.
- **Self-check**: where (which value) does the axis switch from linear to log
  behaviour, and how did you locate it?

## 4. UNIT_PREFIX — 单位词头误读 (mV read as V)

- **Fingerprint**: axis says mV / µV / uV / μV / kV / ms / kHz while the table or
  the output contract expects V / s / Hz; values off by 10³–10⁶.
- **Why agents fall**: the number "3.2" is copied from the axis while the prefix
  letter is dropped; µ/u/μ variants are normalized away or ignored.
- **Detector**: parse unit strings (prefix + base unit, plus `×10^n` axis
  multipliers); same base unit but different multiplier between axis unit and any
  `table_units` entry → fire with the exact factor.
- **Repair**: normalize to the contract's expected unit *before* filling
  result.json; write the conversion ("mV → V, ×1e-3") into `sources`.
- **Self-check**: what is the final reported unit, what factor was applied, and one
  raw→converted value pair as evidence?

## 5. PERCENT_FRACTION — 百分数与分数混淆

- **Fingerprint**: axis in % (0–100) while tables/contract use fractions (0–1), or
  vice versa; ‰ appears in materials.
- **Why agents fall**: "0.35" and "35%" are the same number conceptually, so the
  conversion feels optional — until a downstream field is off by 100×.
- **Detector**: unit parse resolves %, ‰, fraction to a common `fraction` base with
  multipliers 1e-2 / 1e-3 / 1; differing multipliers → fire.
- **Repair**: pick the contract's form, convert once, explicitly; record which form
  is reported in `sources`; if the contract is silent, flag the ambiguity in
  `uncertainty`.
- **Self-check**: is 0.35 in the figure reported as 0.35 or as 35? Which does the
  contract expect — where did you check?

## 6. DUAL_AXIS — 双轴错配

- **Fingerprint**: two y-axes (left/right tick columns, often two units, e.g. "°C"
  and "mm"); series A is read against series B's axis.
- **Why agents fall**: there is only one pixel coordinate system, so whichever tick
  column is more salient calibrates *all* series.
- **Detector**: card structure — ≥2 y axes in one panel with different `side` or
  different `unit_verbatim` strings.
- **Repair**: bind each series to its axis by legend color/marker BEFORE reading any
  value; record the binding (series → side + unit) in `sources`; read each series
  only against its own ticks.
- **Self-check**: for each series, which axis (side + unit) did you read it against,
  and what visual evidence on the zoomed legend proves the binding?

## 7. TRUNCATED_ORIGIN — 截断纵轴夸大差异

- **Fingerprint**: bar chart whose value axis starts at e.g. 40 instead of 0; a 55
  vs 50 difference looks like a 3× effect.
- **Why agents fall**: bar *height* is the visual channel for magnitude; the missing
  baseline is invisible unless you read the lowest tick.
- **Detector**: bar-like chart (`chart_type` contains "bar") and value-axis
  `range[0] > 0`; report visible fraction of full range and the zero-baseline
  exaggeration ratio.
- **Repair**: report absolute values AND state the distortion quantitatively; never
  quote bar-height ratios as value ratios.
- **Self-check**: quote one pair of bars — value ratio and pixel-height ratio; did
  you report only the value ratio as the finding?

## 8. CROPPED_AXIS — 轴被裁切

- **Fingerprint**: the curve runs out of the panel, or the top/bottom of the axis is
  cut by figure cropping; extreme values are unmeasurable.
- **Why agents fall**: the visible portion reads fine, so the missing portion is
  never noticed; extrapolation fills the gap silently.
- **Detector**: element-inventory bboxes extending past the plot-area bbox, or data
  ink touching panel edges.
- **Repair**: report only inside the readable range; values outside are declared
  gaps in `uncertainty` — never extrapolate past the crop.
- **Self-check**: which contract fields are affected by the cropped range, and are
  they marked as gaps with limits stated?

## 9. NONDATA_STAR — 显著性星号被当作数据点

- **Fingerprint**: small `*` / `**` / `***` glyphs floating above bars or boxplots;
  a digitizer harvests them as outlier points.
- **Why agents fall**: a star is a small dark blob at a definite (x, y) — exactly
  what a point detector looks for.
- **Detector**: connected-component analysis of neutral dark ink inside the plot
  bbox; small blobs (4–42 px) with ~radial ink distribution (low octant-radius
  variance, ≥7/8 octants populated), boosted when floating above a bar from the
  element inventory.
- **Repair**: exclude from all data series; record as a significance annotation:
  compared groups + star count.
- **Self-check**: did any digitized "point" coincide with a star bbox? Confirm none
  did, or list the removed points.

## 10. NONDATA_BRACKET — 显著性括号被当作数据

- **Fingerprint**: long thin horizontal line with short vertical end caps spanning
  two bars/groups, usually with a star at its centre.
- **Why agents fall**: brackets look like error bars or fit lines to a shape-based
  reader.
- **Detector**: elongated components (width ≥ 30 px, aspect ≥ 2.5) with one dominant
  horizontal ink row AND vertical end caps at both run ends (distinguishes legend
  line samples and error-bar caps); boosted above bars.
- **Repair**: exclude; record which two groups the bracket connects — it defines
  the comparison the stars refer to.
- **Self-check**: which groups does each bracket connect, and is that pairing in
  `sources`?

## 11. FIT_LINE — 拟合线被当作数据

- **Fingerprint**: regression/trend line drawn through a scatter; digitized as a
  dense series of "data points" with suspiciously zero noise.
- **Why agents fall**: the line is the most salient continuous structure in the
  panel; point-wise digitization cannot tell model from measurement.
- **Detector**: RANSAC on ink pixels (excluding star/bracket components and
  near-axis-aligned ink): a line with many inliers spanning ≥45% of the panel's max
  dimension is a candidate.
- **Repair**: exclude; report slope/intercept ONLY if the task asks, labelled "fit",
  never as observed data.
- **Self-check**: if a slope was reported, is it labelled fit with the excluded
  pixel extent noted? If not asked, is it kept out of result.json values?

## 12. INSET_AXIS + LEGEND_SWAP — 插图轴忽略 / 图例错换

- **INSET_AXIS 插图轴**
  - *Fingerprint*: small framed axes inside the main plot (zoom-in or secondary
    view) with their own ticks.
  - *Why agents fall*: inset pixels get calibrated against the *main* axes, or the
    inset is ignored entirely and its contract field stays empty.
  - *Detector*: components forming a rectangular frame (ink concentrated on the
    bbox border, low fill) sized 15–65% of the panel.
  - *Repair*: read inset content only against inset ticks; if the inset is a zoom,
    prefer it for fine structure in its range.
  - *Self-check*: show one inset value converted with inset calibration.
- **LEGEND_SWAP 图例错换**
  - *Fingerprint*: two or more similar series; legend overlapping the plot area;
    series names swapped in the output.
  - *Why agents fall*: binding name→color is done once, globally, and never
    re-verified; similar hues (blue/teal) swap easily.
  - *Detector*: card `legend_bbox` intersecting the plot-area bbox (legend ink
    inside the data region) + ≥2 legend entries.
  - *Repair*: verify the name→color/marker binding on the zoomed legend itself
    before attributing any value; anchor at the legend swatch, not at a data point.
  - *Self-check*: state the final binding and the zoom evidence; argue why no two
    series could be swapped.

---

## figure_card.json schema

Written by the agent in step 1, from direct inspection of the zoomed figure. All
detectors consume it.

```json
{
  "figure_file": "figure1.png",
  "chart_type": "line | bar | scatter | box | multi-panel: line+bar | ...",
  "axes": [
    {
      "id": "top_y",
      "panel": "top",
      "orientation": "y",
      "side": "left",
      "chart_type": "line",
      "label_verbatim": "Potential (mV)",
      "unit_verbatim": "mV",
      "declared_type": "linear | log | symlog | categorical",
      "ticks": [{"value": 0.001, "pixel": 123.4, "label_verbatim": "10⁻³"}],
      "range": [0.001, 10]
    }
  ],
  "legend": [{"name": "Control", "color": "#1f77b4", "marker": "square"}],
  "legend_bbox": [x0, y0, x1, y1],
  "plot_area_bbox": [x0, y0, x1, y1],
  "element_inventory": [
    {"type": "bar", "panel": "bottom", "bbox": [x0, y0, x1, y1], "note": "Control grp1"}
  ],
  "table_units": ["V", "s"]
}
```

Field rules:

- `axes[]`: one entry per axis per panel. `ticks` needs **≥3 numeric ticks** with
  measured pixel positions for the geometry fit; keep `label_verbatim` for the raw
  glyph string. `declared_type` is what *you* believe the axis is — the detector's
  job is to contradict you when the geometry disagrees.
- `chart_type` may be set per-axis (overrides the global one for that axis) — use
  this in multi-panel figures so the truncated-origin check only fires on the bar
  panel.
- `plot_area_bbox`: single `[x0, y0, x1, y1]` **or** a dict `{"panel": [...]}` for
  multi-panel figures. Measure it on the actual image (spine corners), not from
  memory.
- `legend_bbox`: optional; enables the LEGEND_SWAP overlap check.
- `element_inventory`: optional but boosts star/bracket confidence (`type: "bar"`
  entries); also feeds the CROPPED_AXIS check.
- `table_units`: verbatim unit strings harvested from the shipped tables/captions —
  the unit-prefix screen compares axis units against these.
