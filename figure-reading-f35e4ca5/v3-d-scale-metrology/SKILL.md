---
name: scale-bar-metrology
description: Quantitative measurement from microscopy figures via scale-bar calibration — never trust stated magnification. Detect the scale bar, calibrate nm-per-pixel from the verbatim label, measure particles/segments with propagated uncertainty. 显微图像比例尺标定与定量测量:粒径统计、层厚、间距. Triggers: 比例尺, 标尺, 显微图像, 粒径统计, scale bar calibration, microscopy measurement, particle sizing, nm per pixel.
---

# Scale-Bar Metrology 显微比例尺定量测量

## Core idea

For microscopy-style figures (SEM/TEM/optical/AFM), the quantitative content lives in the **scale bar**, not in the axes (there usually are none) and **never** in a stated magnification. Any resampling, resaving, or rendering step changes the pixel-to-magnification mapping, so "×20,000" is metadata, not a measurement basis. Base agents either trust that stated magnification or eyeball feature sizes. This skill performs real metrology: detect the scale bar's pixel geometry, read its label **verbatim** from a zoomed crop the script prepares, derive physical-units-per-pixel, then measure features (particle sizes, counts, layer thicknesses, agent-marked distances) with calibration-propagated uncertainty on every number. If no bar exists, no measurement is possible — say so, do not invent one.

## Runtime contract

Read `/input/case.json` and `/input/task.md` first; the case's `output_contract` defines the exact result fields (any shape — dict, list, or mixed). Work in `/app/work`; final artifacts belong in `/app/output`, including `result.json` carrying the original `case_id` and every output_contract field. Budget is tight (~900 s, 64 model calls): write a valid **partial** result.json early; improve it in place and keep `status` honest (`success` only when every contract field is filled and every claim is locatable; otherwise `partial` with explicit limits). The case ships ONE original figure image plus all original tables; any figure mentioned in text or captions whose pixels are not provided is a declared gap — list it, never reconstruct it. If paths differ outside the harness, pass the real paths with the CLI flags.

## Dependencies

Python 3 stdlib + numpy 2.x + PIL 12.x. matplotlib 3.x is used **only** for the annotated preview in step 4 (`metrology_result.py`); the detection and measurement scripts (steps 1 and 3) do not import it. No network, no pip. Poppler tools are available in the harness if the figure arrives as a PDF page that must be rasterized first (`pdftoppm -png -r 300`).

## Workflow

All scripts live under `/skills/weekly-skill/scripts/`. Paths below use the harness layout; use the CLI flags when they differ.

**Step 0 — write a partial result.json early (manual, before any script).**
Read `/input/case.json` and `/input/task.md`. Write `/app/output/result.json` with `case_id`, every `output_contract` field (fill with `null` or best placeholders), `"status": "partial"`, empty `sources`/`uncertainty` blocks to be completed later. This guarantees a valid deliverable even if later steps run out of budget.

**Step 1 — detect the scale bar.**
```
python3 /skills/weekly-skill/scripts/find_scalebar.py \
    --image /input/figure.png --work /app/work --out /app/work
```
Outputs `/app/work/scalebar_candidates.json`: each candidate has bbox, `length_px`, orientation, and the path of a **zoomed label crop** PNG (region above/below the bar, 3× upscaled, contrast-stretched). Read that crop image and transcribe the label **verbatim** (e.g. "500 nm", "2 µm"). Exit 2 means no candidate: use the manual-endpoint fallback (see Failure catalogue) or accept "no calibration possible".

**Step 2 — agent writes calibration.json (manual step, this is the human-in-the-loop point).**
Write `/app/work/calibration.json` yourself:
```json
{"length_value": 500, "unit": "nm", "length_px": 200, "endpoint_uncertainty_px": 2,
 "candidate_index": 0, "verbatim_label": "500 nm",
 "bar_bbox": [x, y, w, h], "panel_bbox": [x, y, w, h]  /* panel_bbox only for composites */}
```
- `length_value` + `unit` come from the label you read; `length_px`, `endpoint_uncertainty_px`, `bar_bbox`, `candidate_index` come from the chosen candidate (or from your manually marked endpoints in the fallback path).
- Units: normalize `um`/`µm`/`μm`/`micron` → `µm`; the measurement script also normalizes, but record what you actually read in `verbatim_label`.
- Composite figures: one calibration **per panel**; run step 3 once per panel with its own `panel_bbox`.

**Step 3 — measure features.**
```
python3 /skills/weekly-skill/scripts/measure_features.py \
    --image /input/figure.png --calibration /app/work/calibration.json \
    --marks /app/work/marks.json --work /app/work --out /app/work
```
`--marks` is optional and selects **marked-segment mode** (`marks.json`: `[{"id": "t1", "p0": [x,y], "p1": [x,y], "note": "layer thickness"}, ...]` — you draw the segments; use it for layer thicknesses, spacings, or any non-segmentable feature). Without `--marks`, the script runs **particle mode**: background flattening, Otsu threshold, connected components, per-object area / equivalent diameter / centroid / bbox, converted to physical units. Border-touching and sub-3×3-px objects are excluded and reported. Outputs `measurements.json` (calibration echo with provenance, objects table, segments table, summary stats with uncertainty) and `measurements.csv`.

**Step 4 — assemble the metrology fragment.**
```
python3 /skills/weekly-skill/scripts/metrology_result.py \
    --image /input/figure.png --measurements /app/work/measurements.json \
    --out /app/output
```
Renders an annotated preview PNG into `/app/output` (bar in red, objects outlined and numbered, marked segments drawn, calibration caption) — **inspect it yourself** to sanity-check segmentation before trusting any number — and writes `result_fragment.json` with units on every number, a provenance block (bar bbox, verbatim label, candidate source), an uncertainty block, and a status suggestion.

**Step 5 — fill result.json (manual).**
Merge `result_fragment.json` into the `output_contract` fields of `/app/output/result.json`. Keep `status` honest: `success` only if every contract field is filled, the preview looked correct, and every claim is locatable (bar bbox, object indices, segment ids); otherwise `partial` with explicit limits. List declared gaps (figures mentioned but not shipped). Cite sources: the figure file, the tables, and the calibration provenance.

## Failure catalogue

| Failure | Handling |
|---|---|
| No scale bar found (exit 2) | Fallback: you mark the bar endpoints manually — write `{"p0": [x,y], "p1": [x,y], "verbatim_label": "..."}` into `/app/work/manual_bar.json` and rerun `find_scalebar.py --manual-bar /app/work/manual_bar.json`; if no bar exists at all, status `partial` with explicit "no calibration possible — no scale bar in figure". Never guess a length. |
| Multiple bars / scale bars per panel | Calibrate **per panel**, one calibration.json + one measure run per panel with its `panel_bbox`. Never share calibration across panels — panels may be rendered at different scales. |
| Tilted bar | Use endpoint distance (the script reports both horizontal/vertical and Euclidean length); orientation is flagged `tilted`. Endpoint uncertainty still ±2 px per endpoint. |
| Stated magnification only | Refuse to convert sizes from magnification. Record it as metadata (`"stated_magnification": "×20000 (metadata only, not used)"`) and mark size fields unmeasurable unless a bar exists. |
| Units ambiguous | Normalize `µm`/`um`/`μm`/`microns` → `µm`; `nm` stays `nm`; `mm` stays `mm`. Keep the raw label string in `verbatim_label` so normalization is auditable. If the label is unreadable even in the zoomed crop, status `partial` — do not guess the number. |
| Upscaled composite image | Per-panel calibration is mandatory; an upscaled render invalidates any single global scale. Detect bars panel by panel. |
| Segmentation looks wrong in preview | Threshold-based sizing is not semantic segmentation: fused particles, shadows, and contrast gradients break it. Fall back to `--marks` segments for the critical features and report count as a lower bound. |

## Limits

- Not a semantic segmenter. Particle mode is threshold-based; it is valid only for sparse, contrast-separated objects. The agent must sanity-check the annotated preview before trusting counts/sizes and must state exclusion criteria (border-touching, <3×3 px, fused objects).
- No composition, crystallinity, phase, or chemistry inference — this skill measures geometry only.
- Stated magnification is metadata, never a measurement basis.
- Honesty rules: every number carries a unit and an uncertainty; every claim is locatable (bar bbox, object index, segment id); declared gaps are listed, never reconstructed; `success` requires the full contract filled and verified, otherwise `partial` with explicit limits.
