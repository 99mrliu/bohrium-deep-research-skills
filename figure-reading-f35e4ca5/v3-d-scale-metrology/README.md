# scale-bar-metrology — README

Quantitative metrology for microscopy-style scientific figures (SEM/TEM/optical/AFM):
detect the scale bar, calibrate physical-units-per-pixel from its pixel length and its
verbatim label, then measure particles or agent-marked segments with
calibration-propagated uncertainty. Stated magnification is recorded as metadata only —
after any resampling/rendering it is not a measurement basis.

## Dependencies

Python 3 (stdlib only) + numpy 2.x + PIL 12.x. matplotlib 3.x is required **only** by
`scripts/metrology_result.py` (annotated preview). No network, no pip.

## Inputs

- One original figure image (PNG/JPEG/TIFF readable by PIL).
- `calibration.json` (written by the agent after reading the zoomed label crop):
  ```json
  {"length_value": 500, "unit": "nm", "length_px": 200, "endpoint_uncertainty_px": 2,
   "candidate_index": 0, "verbatim_label": "500 nm", "bar_bbox": [x, y, w, h],
   "panel_bbox": [x, y, w, h]}
  ```
  `panel_bbox` is optional and used for composite figures (one calibration per panel).
- `measurements.json` / `marks.json` (optional): agent-drawn measurement segments
  `[{"id": "t1", "p0": [x, y], "p1": [x, y], "note": "layer thickness"}]`.

## Outputs

- `scalebar_candidates.json` — bar candidates: bbox, length_px, orientation, label-crop path.
- `measurements.json` — calibration echo with provenance (bar bbox + verbatim label),
  objects table, segments table, summary stats (count / mean±sd / median, with units and
  uncertainty). `measurements.csv` — same object table as CSV.
- `result_fragment.json` — ready-to-merge fragment for the case `result.json`: every number
  carries a unit; provenance and uncertainty blocks; status suggestion.
- Annotated preview PNG — bar in red, objects outlined/numbered, segments drawn, calibration
  caption. The agent must inspect it before trusting the numbers.

## Uncertainty propagation

Bar pixel length `L_px` has endpoint uncertainty `u_px` (±1–2 px per endpoint; scripts use
the value in calibration.json, default 2). Relative calibration uncertainty:

    u_rel = u_px / L_px

- Physical scale: `s = length_value / L_px` (unit/px), with the same `u_rel`.
- Any length `d = s · d_px`: `u(d) = d · u_rel` (plus per-segment endpoint error
  ±1.5 px per endpoint → ±√2·1.5 px on marked segments, added in quadrature).
- Any area `A = s² · A_px`: `u(A) = 2 · A · u_rel` (relative uncertainty doubled).
- Mean diameters are reported as `mean ± sd` (sample sd) and the calibration term
  separately, so both the population spread and the metrology floor are visible.

## Exit codes

All three scripts: `0` = success, `2` = valid run but no usable result (e.g. no scale-bar
candidate found, no objects after filtering — read stdout/JSON for fallback instructions),
`1` = error (bad arguments, unreadable file, invalid calibration JSON).

## Limitations

- Threshold-based particle sizing is valid only for sparse, contrast-separated objects;
  it is not semantic segmentation. Fused particles, shadows, and strong illumination
  gradients break it — use `--marks` for critical features.
- No composition/crystallinity/chemistry inference; geometry only.
- A figure with no scale bar admits no measurement — report "no calibration possible".

## Maintenance

- The connected-component labeling is a pure-numpy BFS (no scipy) — keep it that way.
- If label crops come back unreadable for a new figure style, adjust the crop padding /
  contrast-stretch parameters in `find_scalebar.py` (constants at top of file).
- Test with `examples/make_synthetic_case.py` after any change; the synthetic case has
  known ground truth (blob diameters 60–160 px, bar exactly 200 px) and the pipeline
  should recover the mean diameter within propagated uncertainty.
