# Image quality triage — thresholds and degradation playbook

This file is the authoritative reference for the quality verdicts emitted by
`scripts/supply_images.py` and for what the reading agent must do when a
verdict fires. Thresholds below are mirrored by the constants at the top of
`supply_images.py`; if one changes, change the other.

## Triage thresholds

| metric | threshold | verdict |
|---|---|---|
| dpi-equivalent estimate (`width / 6.5 in`) | < 150 | `low_resolution` |
| megapixels | < 0.5 MP (also < 0.1 MP → class `very_low`) | `low_resolution` |
| min(width, height) | < 200 px | `tiny_dimension` |
| overexposed fraction (luminance > 250) | > 20% **and** border median ≤ 250 (i.e. not a white-background graphic) | `overexposed` |
| underexposed fraction (luminance < 5) | > 60% **and** border median ≥ 5 (i.e. not a dark-background figure) | `underexposed` |
| clipped fraction either way | > 95% | `mostly_blank` |
| contrast spread (p95 − p5) | < 40 / 255 | `low_contrast` |
| blur proxy (variance of gradient magnitude) | < 30 | `blurry` |
| aspect ratio | height > 1.8 × width | `possibly_rotated` (flag only) |
| no verdicts fire | — | `ok` |

Resolution classes: `high` ≥ 2 MP, `medium` ≥ 0.5 MP, `low` ≥ 0.1 MP,
`very_low` < 0.1 MP. The dpi-equivalent is a heuristic: it assumes the figure
would be printed ~6.5 inches wide. Treat it as an order-of-magnitude signal,
not a metrology result.

## Degradation playbook

### Cropped axis
The figure was cut so some tick labels or the axis title are missing.
- **Declare the missing ticks explicitly** in `result.json`'s `uncertainty`.
- Read only **between surviving ticks**: you may interpolate a point against
  two intact, labeled ticks; you may not extrapolate past the last surviving
  labeled tick.
- If an axis title is cropped, report the quantity only if the surviving
  ticks + caption/table evidence identify it; otherwise mark the field
  partial.

### Overexposure / underexposure
- Zoom tiles are percentile-stretch normalized (p2–p98), which usually
  recovers faint labels; read from the **tile**, not the raw page view.
- If a channel is clipped (pure white/black regions where content should be),
  say so and widen the reported uncertainty — clipped pixels carry no
  information and no processing can restore them.

### Low resolution (< 150 dpi-equivalent, class `low`/`very_low`)
- State in `uncertainty`: reading error ≥ **half a tick interval** on that
  axis. Tick labels may be confusable (3 vs 8, 1 vs 7); cross-check against
  the original tables when available.
- Never report more significant figures than the tick spacing supports.

### Rotation
- `possibly_rotated` is a flag, not a fix. Do **not** auto-rotate unless the
  rotation is obvious (e.g. text clearly sideways in every tile).
- If you must read a rotated figure, note it and read along the rotated axes
  carefully; record the rotation in `uncertainty`.

### PDF-shipped figures
- Pages are rendered at 400 dpi with `pdftoppm`; prefer the rendered PNG over
  any embedded low-res preview. If `pdftoppm` was missing (`degraded:
  ["pdftoppm_missing"]`), the figure pixels may be unavailable — that is a
  declared gap, not something to reconstruct.

## Why provenance is mandatory

Every reported value must cite (a) the **tile filename** it was read from and
(b) the tile's **original-image pixel bbox** from `zoom_manifest.json` /
`panels.json`. This makes each claim locatable and auditable: anyone can crop
the same rectangle from the original image and check the reading. A value
without tile+bbox provenance is not reportable under this skill — if you
cannot cite where you read it, mark the field partial instead.
