# Measurement protocol

## When threshold-based particle sizing is valid

`measure_features.py` particle mode is valid only when **all** of the
following hold:

- Objects are **sparse**: they do not touch or overlap each other.
- Objects are **contrast-separated**: clearly darker (or clearly brighter)
  than a slowly varying background.
- Objects are compact (roughly equiaxed); highly elongated or branching
  shapes make "equivalent diameter" a poor descriptor — report it anyway but
  flag the shape caveat.

The annotated preview is the check: open it and verify that (a) every visible
particle has exactly one outline, (b) no outline covers background or two
fused particles, (c) the bar/label/legend are not outlined. If any check
fails, the numbers are not trustworthy as population statistics.

## When the agent must mark segments manually

Use `--marks` with agent-drawn `[p0, p1]` segments whenever the feature of
interest is not a thresholdable blob:

- **Layer thicknesses** in cross-section images (measure several segments
  along the layer, report each + their spread).
- **Spacings / pitches** (lattice-like patterns, groove spacing).
- **Fused or touching particles** where only a few individual widths can be
  picked out by eye.
- Any feature on a **graded or textured background** where the preview shows
  segmentation artifacts.

Marked segments are also the right fallback for a "sanity triangulation":
measure 3–5 representative particles by hand and compare with the automatic
mean; disagreement beyond the combined uncertainty means the segmentation is
biased — trust the marks, not the threshold.

## Border-touching and fused-particle caveats

- Objects touching the image/panel border are **excluded** (their true extent
  is unknown) and listed under `excluded` with the reason. State this in the
  result: the count is a count of *fully visible* objects.
- Objects with a bbox side < 3 px are excluded as likely noise/texture.
- **Fused particles** count as one object and bias the mean diameter upward.
  If the preview shows fusion, report the count as a *lower bound* and the
  mean as an *upper bound*, and prefer `--marks` for the size estimate.
- The scale bar and its label region are masked out before segmentation so
  they are never counted as particles.

## Uncertainty propagation rules used by the scripts

Given bar pixel length `L_px` with per-endpoint uncertainty `u_px`
(default ±2 px) and label value `V` (unit `U`):

```
scale  s     = V / L_px            [U/px]
u_rel        = u_px / L_px         (relative calibration uncertainty)

length  d    = s · d_px            u(d) = d · u_rel
area    A    = s² · A_px           u(A) = 2 · A · u_rel
segment d    = s · d_px            u(d) = s · sqrt( (d_px·u_rel)² + 2·(1.5 px)² )
```

- Relative uncertainty doubles for areas (two powers of the scale).
- Marked segments additionally carry the ±1.5 px endpoint error of *your*
  clicks, added in quadrature — for short segments this dominates the
  calibration term.
- These terms cover **calibration and endpoint placement only**. They do not
  cover segmentation bias (threshold choice shifting edges by ~1 px) or
  sample selection bias. When comparing two measured values, use the combined
  quadrature sum; when comparing against an external (e.g. ground-truth or
  literature) value, also consider the standard error of the mean.

## How to report count / mean ± sd honestly

- Always report `n` (the count of measured objects) alongside any mean.
- Report **mean ± sd** (sample standard deviation = population spread), not
  just mean ± calibration uncertainty; the scripts give sd, sem, and the
  calibration term separately. The calibration term is the metrology floor
  that applies even to a perfect measurement.
- State the exclusion criteria with the numbers (border-touching, <3×3 px,
  bar/label masked, fused objects counted once).
- If objects were measured in multiple panels with separate calibrations,
  never pool raw pixel values — pool the physical values, or better, report
  per-panel statistics.
- Keep units on every number, and keep the verbatim scale-bar label in the
  provenance block.
