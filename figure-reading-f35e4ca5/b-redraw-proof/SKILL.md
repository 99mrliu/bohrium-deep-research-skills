---
name: redraw-proof-figure-reading
description: Extract data from a scientific figure and PROVE the extraction by re-rendering the figure from the read data and pixel-diffing the reconstruction against the original — a downstream rendering-engineering loop (spec -> deterministic replot -> affine-registered overlay diff -> verdict) where readings ship only when the redraw reproduces the original ink. Use when a task requires figure data extraction, chart reconstruction, or verified numeric reading (图表重绘验证, figure digitization with proof, reconstruction diff) and unaudited eyeball numbers are unacceptable.
---

# Redraw-proof figure reading

Core idea: **a reading you cannot redraw is a reading you cannot trust.**
The deliverable is not just numbers but a rendering proof: the agent
declares everything it read in a validated `figure_spec.json`, a
deterministic renderer rebuilds the figure from that spec, and a
pixel-level overlay diff against the original accepts or rejects the
reading. Deliverables include the reconstruction PNG/PDF/SVG, the diff
map, and metrics — rendering engineering as verification.

## Runtime contract

Read `/input/case.json` and `/input/task.md` first; `output_contract`
defines the result fields. Work in `/app/work`; final artifacts in
`/app/output`, including `result.json` with the original `case_id` and
every contract field. Budget ~900 s / 64 model calls: write a partial
result.json early (step 5's make_result works with a null fragment),
then improve. `status` stays honest: `success` only when the diff verdict
is not `rejected` AND every contract field is filled. Outside the harness,
pass real paths via the CLI flags.

## Dependencies

`numpy`, `pillow`, `matplotlib` (preinstalled in the scientific runtime).
`replot.py` exits 3 honestly if matplotlib is missing; `overlay_diff.py`
exits 3 if numpy/PIL is missing — in that case fall back to the manual
reading discipline of `references/spec_format.md` and record the degraded
verification in `uncertainty`. No network, no pip install.

## Workflow

1. **Read the case and measure the figure's geometry.** Zoom/crop the
   figure (PIL; `pdftoppm -png -r 300` if it ships in a PDF). Record the
   plot-area pixel box `[left, top, right, bottom]` and ≥3 tick
   positions per axis.

2. **Author the spec** `/app/work/figure_spec.json` following
   `references/spec_format.md`: verbatim axis labels and units, axis type
   decided by tick labels (constant difference → linear; constant ratio →
   log), series with data-coordinate points / bar values+errors,
   legend-verbatim names, `#rrggbb` colors sampled from the ink,
   meaningful annotations only.

3. **Validate.**
   `python /skills/weekly-skill/scripts/to_spec.py --spec /app/work/figure_spec.json --out /app/work/spec_canonical.json`
   Exit 2 = fix the spec; warnings (missing error semantics, no unit in
   label) must be resolved against the caption, not ignored.

4. **Re-render.**
   `python /skills/weekly-skill/scripts/replot.py --spec /app/work/spec_canonical.json --out /app/output/reconstruction`
   Produces reconstruction.png (300 dpi) + .pdf + .svg (editable text)
   + .meta.json (plot-area pixel geometry).

5. **Diff against the original.**
   `python /skills/weekly-skill/scripts/overlay_diff.py --original <fig> --orig-plot-area L,T,R,B --recon /app/output/reconstruction.png --meta /app/output/reconstruction.meta.json --spec /app/work/spec_canonical.json --out /app/output/verify`
   Verdicts per `references/diff_metrics.md`: `verified` ships;
   `plausible` ships with the mismatch regions stated; `rejected` means
   the spec is wrong — inspect `worst_cells` and `per_series_recall`,
   re-read those regions at higher zoom, patch only the implicated
   entries, re-render, re-diff.

6. **Deliver.**
   `python /skills/weekly-skill/scripts/make_result.py --case /input/case.json --fragment /app/work/result_fragment.json --metrics /app/output/verify.metrics.json --out /app/output/result.json --status success`
   `make_result.py` refuses `success` on a rejected verdict or null
   contract fields. `/app/output` should hold: result.json,
   reconstruction.{png,pdf,svg}, verify.diff.png, verify.metrics.json.

## Failure catalogue

| Symptom | Diagnosis | Fix |
|-|-|-|
| verdict rejected, uniform red shift | plot-area box wrong or axis origin misread | re-measure `--orig-plot-area` at high zoom |
| one series red | legend mapping swapped / curve dropped | fix that series only (per_series_recall isolates it) |
| red at one x region | local misread | re-read that region; check worst_cells |
| low precision, high recall | invented points/annotations | delete spec entries with no figure counterpart |
| bars fine but recall capped ~0.8 | original gridlines are ink with no spec counterpart | state the cause in uncertainty, or note grid in annotations |
| matplotlib missing | degraded runtime | manual reading per spec_format.md; record degraded path |

## Limits

- 2-D Cartesian charts (line/scatter/bar). Heatmaps, 3-D, pie charts and
  micrographs: read manually, mark `unable_to_verify` in uncertainty —
  the diff loop does not apply.
- Categorical x axes are rendered as bar categories; line plots over
  categories should use numeric x indices with a note.
- Multi-panel figures: one spec + one diff **per panel**.

See `examples/minimal_example.md` for a complete runnable synthetic
miniature (illustrative, not an official case result).
