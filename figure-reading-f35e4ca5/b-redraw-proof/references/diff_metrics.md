# Overlay diff metrics and verdicts

`overlay_diff.py` registers the reconstruction onto the original via the
two plot-area boxes (an affine scale+translate per axis — robust to
different margins, fonts and figure sizes), extracts ink masks inside the
plot area, and measures coverage at `--tol-px` tolerance (default 4 px in
original-image pixels).

## Metrics

- **ink_recall** — fraction of original ink pixels that lie within tol of
  reconstruction ink. This is THE reading-quality metric: every curve,
  marker and bar edge in the original must be explained by the spec.
- **ink_precision** — fraction of reconstruction ink supported by original
  ink. Lower than recall by design (gridlines, tick marks and text inside
  the plot area belong to the original only); a very low precision means
  invented data.
- **per_series_recall** — recall restricted to pixels matching each spec
  color. Localizes which series is misread (a swapped legend shows up as
  two series both near 0.5).
- **worst_cells** — the 5 plot-area grid cells with the lowest recall.
  Fix readings in these cells first; do not re-read the whole figure.

## Verdicts

| verdict | rule | meaning |
|-|-|-|
| verified | recall ≥ 0.85 and precision ≥ 0.70 | reconstruction reproduces the figure; readings accepted |
| plausible | recall ≥ 0.60 | substantial agreement; residual mismatch — inspect worst cells, report limits |
| rejected | recall < 0.60 | the spec does not describe this figure; readings must not ship |

`make_result.py --metrics` refuses `status: success` on a rejected
verdict. Plausible verdicts may ship as success only when the answer text
states the mismatch regions and their cause.

## Typical failure → fix

| Symptom in diff map | Cause | Fix |
|-|-|-|
| whole curve shifted vertically | y calibration wrong (plot-area top/bottom off, or axis not starting at first tick) | re-measure y ticks, correct spec points |
| one series red, rest green | legend mapping swapped or one curve skipped | re-read legend colors; fix the series in the spec |
| red only at markers | marker positions right, marker *size* differs, or dashed line gaps | acceptable; check per-series recall instead of global |
| red gridlines everywhere | original has grid, reconstruction doesn't | add grid to the original exclusion: recall counts ink inside the plot area — gridlines are original ink; either draw the grid in the spec (matplotlib `ax.grid(True)` via annotations note) or accept the recall ceiling and state it |
| bars right heights, wrong x | category order mismatch | match category order verbatim to the axis labels |

## Iteration loop

1. diff → worst cells → re-read those regions at higher zoom
2. patch ONLY the implicated spec entries
3. re-render, re-diff; stop when verified or when remaining misses are
   demonstrably non-data ink (gridlines, arrowheads) — then ship with the
   cause stated.
