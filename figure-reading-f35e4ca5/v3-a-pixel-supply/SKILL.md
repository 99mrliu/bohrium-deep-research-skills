---
name: pixel-supply-figure-reading
description: Deterministic pixel-supply chain for scientific figure reading — image quality triage, panel segmentation (子图切分), axis zoom crops (坐标轴放大), tick-label recognition support (刻度识别), figure tiling, zoom crops; every tile carries original-image pixel provenance so readings are traceable.
---

# Pixel-Supply Figure Reading

## Core idea

A reading agent can only be as good as the pixels it is shown. Base agents fail because they read a full-page figure at screen resolution: tick labels, unit prefixes (m vs µ), and log-axis minor ticks are illegible at that scale. This skill is a **deterministic image-supply chain** that prepares verified, coordinate-traceable pixels **before** any reading happens: quality triage, panel segmentation, and high-resolution zoom tiles of tick / legend / label regions. Every tile carries its bounding box in original-image coordinates, so every value read from a tile can cite its pixel provenance. This skill does **not** digitize curves and does **not** govern process; it only guarantees the agent reads from adequate, traceable pixels.

## Runtime contract

Read `/input/case.json` and `/input/task.md` first; the case's `output_contract` defines the exact result fields (any shape — dict, list, or mixed). Work in `/app/work`; final artifacts belong in `/app/output`, including `result.json` carrying the original `case_id` and every output_contract field. Budget is tight (~900 s, 64 model calls): write a valid **partial** result.json early; improve it in place and keep `status` honest (`success` only when every contract field is filled and every claim is locatable; otherwise `partial` with explicit limits). The case ships ONE original figure image plus all original tables; any figure mentioned in text or captions whose pixels are not provided is a declared gap — list it, never reconstruct it. If paths differ outside the harness, pass the real paths with the CLI flags.

## Dependencies

- python3 with stdlib, numpy 2.x, PIL (Pillow) 12.x — required, preinstalled in the harness.
- matplotlib 3.x — only used by the synthetic example generator, never needed for reading.
- Optional: poppler `pdftoppm` / `pdftotext` for figures that ship inside a PDF. Absence is recorded as a **degraded** flag, never fatal.
- No network. No pip. No ML models, no OCR engines.

## Workflow

Step numbers are stable; commands use the harness install path `/skills/weekly-skill/scripts/...`.

**Step 0 — Secure a partial result.json.** Before any pixel work, read `/input/case.json` and `/input/task.md`, then write a skeleton `/app/output/result.json` containing the original `case_id`, `status: "partial"`, every `output_contract` field filled with a placeholder (`null` or `"pending"`), an empty `sources` list, and an `uncertainty` note. This guarantees a valid deliverable even if the budget runs out mid-way.

**Step 1 — Supply triage.** Inventory and quality-check all materials:

```
python3 /skills/weekly-skill/scripts/supply_images.py --input-dir /input --work /app/work --out /app/output
```

This locates the ONE original figure image (png/jpg/tif), renders PDF-shipped figures with `pdftoppm -png -r 400` when needed, computes per-image quality metrics (size, effective-resolution class, luminance mean/std, over/underexposure fraction, blur proxy, contrast spread), and writes `image_supply.json`. Read its `verdicts` and `degraded` list before proceeding — they tell you which quality caveats must appear in `result.json`'s `uncertainty` field.

**Step 2 — Panel segmentation.**

```
python3 /skills/weekly-skill/scripts/tile_panels.py --image /app/work/<figure.png> --work /app/work --out /app/output/panels
```

This segments multi-panel figures into subfigures with pure-numpy gutter detection (no ML), guesses panel labels (a)/(b)/A/B near each panel's top-left corner, upscales each panel 2×, and writes `panels.json` with each panel's bbox in **original-image coordinates**. Single-panel figures yield one whole-image panel, flagged.

**Step 3 — Zoom tiles.**

```
python3 /skills/weekly-skill/scripts/zoom_regions.py --image /app/work/<figure.png> --panels /app/output/panels/panels.json --out /app/output/zoom
```

For each panel this emits high-resolution, contrast-normalized tiles: left axis strip, bottom axis strip, legend zone, title strip. `zoom_manifest.json` maps every tile to `{panel, region, original-image bbox, scale}`.

**Step 4 — Read ONLY from tiles.** Never read values off the full-page image. For each reading, record the tile filename **and** the original-image pixel bbox from `zoom_manifest.json` / `panels.json` in the result's `sources`. Follow `references/tiling_protocol.md`: axis type from the tick-label tile, units from the axis-title tile, series names from the legend tile. Convert tile-pixel observations back to original coordinates with the manifest scale (see `references/tiling_protocol.md`).

**Step 5 — Assemble result.json.** Update `/app/output/result.json` in place: fill every `output_contract` field, set `status` to `success` only when every field is filled and every claim cites a tile + bbox; otherwise `partial` with explicit limits. List any figure mentioned in text/captions whose pixels were not shipped as a declared gap. Never reconstruct missing figures. Consult `references/image_quality.md` for degradation caveats that must be reflected in `uncertainty`.

## Failure catalogue

| Abnormal input | Script behavior |
|---|---|
| Figure inside a PDF | `supply_images.py` renders pages with `pdftoppm -png -r 400` into the work dir; if `pdftoppm` is missing, records `degraded: ["pdftoppm_missing"]` and continues (exit 2), never fatal |
| Low resolution (<150 dpi-equivalent / small pixel count) | Triage verdict `low_resolution`; zoom tiles still produced; agent must state reading error ≥ half a tick interval (see `references/image_quality.md`) |
| Overexposed / underexposed | Histogram fractions flagged in `image_supply.json` (`overexposed` / `underexposed` verdict); tiles get percentile contrast stretch; agent notes uncertainty |
| Rotated figure | Not auto-rotated unless obviously rotated (aspect + projection heuristics); flagged `possibly_rotated` in triage; agent reads as-is and notes it |
| Cropped axis | Tick-region tiles will show truncated labels; protocol requires declaring missing ticks and reading only between surviving ticks |
| Single-panel figure | `tile_panels.py` emits one panel = whole image with `single_panel: true`; zoom tiles proceed normally |
| Panel labels missing | Label detection is best-effort; absence is a warning (`label_guess: null`) in `panels.json`, not fatal |
| No image materials at all | `supply_images.py` exits 1 (fatal); agent reports `unable` with the reason |

## Limits

- **No OCR.** Tiles make text legible for the *agent's* vision; the scripts never extract text themselves.
- **No curve digitization.** The supply chain stops at delivering traceable pixels; it never converts curves to data series.
- **No interpretation.** Verdicts are mechanical quality flags, not scientific judgments.
- **No process governance.** Reading order and budget discipline are the agent's job; this skill only guarantees pixel adequacy and provenance.
- **Honesty rules:** read only from tiles; record tile + original-image bbox for every value; list declared gaps for figures mentioned but not shipped; keep `status` honest; never reconstruct missing figures; never invent tick values that are illegible even in tiles — report the uncertainty instead.
