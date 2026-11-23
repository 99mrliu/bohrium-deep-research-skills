# Journal export presets

Presets live in `presets/journal_presets.json` and are consumed by
`scripts/export_journal.py` (render) and `scripts/export_check.py` (compliance).

| preset           | width_mm | dpi | font floor/ceiling (pt) | background            | use when |
|------------------|---------:|----:|-------------------------|-----------------------|----------|
| `generic`        | 120      | 300 | 5–9                     | white                 | default; case names no venue |
| `nature_single`  | 89       | 300 | 5–7                     | white                 | Nature-family single column |
| `nature_double`  | 183      | 300 | 5–7                     | white                 | Nature-family full width |
| `science_single` | 86       | 300 | 5–7                     | white                 | Science single column |
| `science_double` | 178      | 300 | 5–7                     | white                 | Science full width |
| `presentation`   | 160      | 150 | 12–28                   | transparent allowed   | slides / posters |

## Parameter explanations

- **mm sizing**: the export rescales the SVG root `width`/`height` to the
  preset width (aspect preserved). The `viewBox` is untouched, so all vector
  geometry scales losslessly. **Compose your figure at the target width**
  (`width_mm` in the compose plan): if you compose at 120 mm and export at
  183 mm, a 7 pt label becomes ~10.7 pt and the font check will (correctly)
  warn.
- **DPI 300 vs 600**: 300 dpi is the standard floor for journal raster art;
  use 600 dpi presets (add one, see below) for line-art-only figures when the
  journal asks. PNGs are rasterized from the exported PDF with
  `pdftoppm -r <dpi>`, so the pHYs chunk carries the true dpi.
- **Font floors**: checked at the *final physical scale*. Below
  `font_min_pt` is illegible in print; above `font_max_pt` looks amateurish in
  a journal figure. Warnings are honest deviations, not silent failures.
- **RGB vs CMYK**: authoring happens in RGB; CMYK conversion happens at the
  publisher. Use the colorblind-safe default palette (Okabe–Ito) and do not
  "pre-convert" colors.
- **Editable text**: journals and this challenge require text to remain real
  `<text>` (never outlined paths) so labels stay correctable. The composer
  sets `svg.fonttype='none'`; `export_check.py` fails a figure whose text is
  all outlines.
- **Background**: most journal presets expect white. matplotlib SVGs have no
  background rect (transparent); if the venue requires white, add a
  full-canvas white rect behind the artwork (a `highlight_region` op is *not*
  the right tool — edit the SVG root or compose with
  `fig.patch.set_facecolor("white")`).

## Adding a custom preset

Append to `presets/journal_presets.json` → `"presets"`:

```json
"elife_single": {
  "name": "elife_single", "width_mm": 85, "dpi": 600,
  "font_min_pt": 5, "font_max_pt": 8,
  "background": "white", "transparent_allowed": false,
  "color_note": "RGB; CMYK conversion happens at the publisher",
  "description": "eLife single column, 600 dpi line art"
}
```

Fields `name`, `width_mm`, `dpi`, `font_min_pt`, `font_max_pt`,
`background`, `transparent_allowed`, `color_note`, `description`. Unknown
preset names fall back to `generic` with a warning on stderr.
