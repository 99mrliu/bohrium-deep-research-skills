# pixel-supply-figure-reading

A deterministic **pixel-supply chain** for scientific-figure reading agents. It does not read figures itself; it guarantees that whatever agent reads the figure does so from adequate, coordinate-traceable pixels: quality-triaged images, segmented panels, and high-resolution zoom tiles of axis/legend/label regions, each carrying its bounding box in original-image coordinates.

## Install

Nothing to install. Copy this directory to `/skills/weekly-skill` (or any path — pass real paths via the CLI flags). The scripts are plain python3 and run in place.

## Dependencies

| Component | Version | Required? |
|---|---|---|
| python3 | ≥3.9 (stdlib only) | yes |
| numpy | 2.x | yes |
| PIL (Pillow) | 12.x | yes |
| matplotlib | 3.x | only for `examples/make_synthetic_case.py` |
| poppler `pdftoppm` / `pdftotext` | any | optional; absence is recorded as degraded, never fatal |

No network access, no pip installs, no ML models, no OCR engines.

## Input requirements

- A case directory (harness: `/input`) containing:
  - `case.json` with at least a `case_id`, an `output_contract` of any shape, and a `materials` list (file names or relative paths).
  - `task.md` — free-text questions.
  - Materials: exactly ONE original figure image (png/jpg/tif) plus original tables. A figure shipped inside a PDF is supported via `pdftoppm`.
- Writable work and output directories (harness: `/app/work`, `/app/output`).

## Commands

```
python3 scripts/supply_images.py --input-dir /input --work /app/work --out /app/output
python3 scripts/tile_panels.py  --image /app/work/<figure.png> --work /app/work --out /app/output/panels [--max-panels 16]
python3 scripts/zoom_regions.py --image /app/work/<figure.png> --panels /app/output/panels/panels.json --out /app/output/zoom
```

## Output field definitions

### `image_supply.json` (from `supply_images.py`)

| field | type | meaning |
|---|---|---|
| `case_id` | str\|null | case id if a case.json was found |
| `inventory` | list | every material file found: `{path, kind}` where kind ∈ `image`, `pdf`, `table`, `text`, `other` |
| `figure_candidates` | list | image files (incl. PDF renders) usable as figure pixels, with `source` (`direct` or `pdf_render`) |
| `images` | dict | per-image metrics keyed by image path (see below) |
| `verdicts` | dict | per-image list of quality verdict strings: `ok`, `low_resolution`, `tiny_dimension`, `overexposed`, `underexposed`, `mostly_blank`, `low_contrast`, `blurry`, `possibly_rotated` (exposure verdicts are background-aware: a white-background line figure is not flagged `overexposed`) |
| `degraded` | list | supply-chain degradations, e.g. `pdftoppm_missing`, `no_image_materials` |
| `fatal` | str\|null | fatal reason, if any |

Per-image metrics (`images[path]`): `width`, `height`, `megapixels`, `resolution_class` (`high` ≥ 2 MP, `medium` ≥ 0.5 MP, `low` ≥ 0.1 MP, `very_low` below), `luminance_mean`, `luminance_std` (0–255), `overexposed_fraction`, `underexposed_fraction` (histogram fractions above 250 / below 5), `blur_proxy` (variance of numpy gradient magnitude; higher = sharper), `contrast_spread` (p95 − p5 of luminance), `dpi_equivalent_estimate` (heuristic assuming a ~6.5-inch-wide figure).

### `panels.json` (from `tile_panels.py`)

| field | type | meaning |
|---|---|---|
| `image` | str | source image path |
| `image_size` | [w, h] | original image size in pixels |
| `single_panel` | bool | true when no internal gutters were found |
| `panels` | list | one entry per detected panel |

Each panel entry: `panel_id` (str, `panel_1`…), `label_guess` (str\|null, e.g. `"(a)"`; best-effort, null = warning only), `bbox_original` (`[x0, y0, x1, y1]` in original-image pixels), `crop_path` (PNG of the panel, margin-padded, upscaled), `scale` (upscale factor, 2.0).

### `zoom_manifest.json` (from `zoom_regions.py`)

| field | type | meaning |
|---|---|---|
| `image` | str | source image path |
| `tiles` | dict | tile filename → `{panel, region, bbox_original, scale}` |

`region` ∈ `left_axis`, `bottom_axis`, `legend_zone`, `title_strip`. `bbox_original` is `[x0, y0, x1, y1]` in original-image pixels. `scale` is the tile's upscale factor relative to the original image (panel scale × strip scale). To map a pixel `(tx, ty)` inside a tile back to the original image: `orig = bbox_original[:2] + (tx, ty) / scale`.

## Error semantics

| exit code | meaning |
|---|---|
| 0 | ok — all steps completed, no degradations |
| 2 | degraded-partial — output files were still written, but check `degraded` / warnings (e.g. missing `pdftoppm`, no panel labels found, single-panel fallback) |
| 1 | fatal — required input missing/unreadable; no usable output; the agent should report `unable` with the printed reason |

## Synthetic example

See `examples/minimal_example.md` for a minimal end-to-end invocation against a synthetic case, and `examples/make_synthetic_case.py` to generate one (`python3 examples/make_synthetic_case.py --out /tmp/demo`). Everything in `examples/` is synthetic demo material (合成示例), never formal case data.

## Limitations

- No OCR, no curve digitization, no interpretation, no auto-rotation beyond an obvious-rotation flag.
- Panel segmentation assumes light background with near-empty gutters between panels; collage-style overlapping panels will be mis-split or merged — check `panels.json` bbox sanity yourself.
- Label detection is heuristic connected-component matching near panel corners; treat `label_guess` as a hint, verify against the title strip tile.
- See `references/image_quality.md` for the degradation playbook and `references/tiling_protocol.md` for the reading protocol.

## Maintenance

- Single-maintainer bundle; keep scripts stdlib+numpy+PIL only — do not add dependencies.
- If thresholds need tuning, change them in one place: the `THRESHOLDS`-style constants at the top of each script, and mirror the change in `references/image_quality.md`.
- Run the synthetic end-to-end test (`examples/minimal_example.md`) after any change to the scripts.
