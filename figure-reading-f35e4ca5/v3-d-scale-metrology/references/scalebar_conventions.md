# Scale-bar conventions and pitfalls

## Why stated magnification is metadata-only

A magnification like "×20,000" is defined relative to a specific display or
print size. The moment a figure is resampled, resaved, cropped, embedded in a
PDF, or rendered at a different DPI — all of which happen between the
microscope and the case file you receive — the pixel-to-magnification mapping
changes, while the *scale bar*, being part of the pixels, resamples together
with the features. That is why the bar is the only trustworthy calibration
source in a shipped figure. Record stated magnification as metadata
(`"stated_magnification": "×20000 (metadata only, not used)"`) and never
convert sizes from it.

## Bar vs axis-inset vs gridline discrimination

Microscopy figures rarely have axes, but composite figures may embed small
plots that do. Do not confuse:

- **Scale bar**: a solid filled rectangle (white or black), no ticks, no
  arrowheads, usually near a corner, paired with a short text label giving a
  physical length. This is the calibration target.
- **Axis / inset plot**: has tick marks, tick numbers, and usually an axis
  title; lines are thin (1–2 px), not filled rectangles. Not usable for
  calibrating the micrograph panel — it calibrates only its own plot.
- **Gridlines / scale grids** (common in TEM): a regular mesh overlaid on the
  image. Only usable if the grid pitch is stated in the caption; otherwise
  treat as uncalibrated.
- **Ruler overlays / stage micrometers**: ticked bars; the distance between
  *numbered* ticks is the calibrated length, not the total bar length. If you
  must use one, mark two numbered ticks with `--manual-bar`.

The detection heuristics in `find_scalebar.py` (aspect ratio, fill ratio,
corner location, plausible length) encode exactly this discrimination, but
the agent must confirm the candidate visually in the label crop.

## Typical label formats

- `500 nm`, `100 nm`, `20 nm`, `5 nm` — TEM/SEM high magnification.
- `2 µm`, `10 µm`, `50 µm` — SEM/optical. Written variously as `µm` (micro
  sign U+00B5), `μm` (Greek mu U+03BC), `um`, or `microns`. All normalize to
  `µm`; the scripts accept all aliases.
- `1 mm`, `200 µm` — optical stereo microscopy.
- Labels may include a space or not (`500nm`), may sit above, below, or
  beside the bar, and may carry a figure-panel letter nearby — read the
  *number + unit* pair that belongs to the bar, not a nearby caption letter.

## Recording the verbatim label as provenance

Always copy the label string exactly as seen (e.g. `"verbatim_label":
"500 nm"`) into calibration.json, alongside the numeric `length_value` and
normalized `unit`. The verbatim string is the audit trail: if a reviewer
disputes a measurement, the crop PNG plus the verbatim string show precisely
what was read. If the label is unreadable even in the 3× contrast-stretched
crop, do **not** guess — status stays `partial`.

## Per-panel calibration in composite figures

Composite figures (panels a–d, insets, EDS maps next to SE images) are
frequently assembled from sources rendered at different scales, and the whole
composite may then be upscaled. Consequences:

- Calibrate **per panel**: run find/measure once per panel, each with its own
  calibration.json and `panel_bbox`.
- **Never share calibration across panels**, even when the bars look
  identical; identical-looking bars with different labels (100 nm vs 1 µm)
  are common.
- An inset inside a panel gets its own calibration if it has its own bar;
  if it has none, its features are unmeasurable — say so.

## Endpoint uncertainty

The scripts assume ±2 px per bar endpoint by default (thresholding and
anti-aliasing make the bar edges fuzzy). For very crisp bars ±1 px is
defensible; for blurry upscaled composites keep ±2 px or worse and widen the
reported uncertainty accordingly — that honesty is the point of propagating
it.
