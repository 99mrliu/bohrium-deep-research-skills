# Read-back verification methodology

## Why geometry read-back

Visual inspection ("looks right") misses exactly the errors that matter in
scientific figures: a series bound to the wrong column still produces a
beautiful bar chart; swapped legend colors are invisible if you don't
re-check; a unit slip (% vs fraction) moves every glyph by a factor the
eye won't catch without a reference. The verifier therefore treats the
saved SVG as the *only* artifact under test and re-derives the data from
**glyph geometry** — the same pixels a reviewer would measure. If the
geometry and the source table agree, the figure cannot be silently wrong
about the values it encodes. The verifier is pure stdlib (xml.etree, re,
math, json, csv, subprocess): it shares no code with the matplotlib
drawer, so a drawer bug cannot simultaneously corrupt the check.

## How the affine fit works

matplotlib emits SVG user units (points). The mapping data→pixel is
affine: `py = a·val + b` (with `a < 0` because SVG y grows downward).

1. Locate each axes group (`<g id="axes_N">`). Tick labels live in
   `<g id="ytick_K">` / `<g id="xtick_K">` subgroups.
2. For each tick, pair the numeric label text with the **tick mark**
   position — the `<use>` glyph inside the same tick group. (The text's
   `y` attribute is the glyph *baseline*, which carries a constant offset;
   fitting against it would bias the intercept by a few points against
   true geometry. Tick marks are exact.)
3. Least-squares fit `a, b` over all ticks of the axis (≥2 required).
   Residuals are ~1e-3 px for matplotlib output.
4. Invert: `val = (py − b) / a`.

Bar charts: x is categorical — category order is recovered from the sorted
x-tick label positions; bar glyphs are matched to categories by the index
embedded in their gid (`bar__p0__WT__3` → 4th category).

## What is read back

- **bars**: each bar is a `<path>` rectangle inside its gid group;
  vertices come from the `d` attribute (M/L commands). Recovered value =
  the far edge from the baseline, sign-aware for negative bars.
- **lines**: the series polyline (`fill:none` path under
  `series__panel__name`); vertices converted point-by-point, x and y.
- **scatter**: `<use>` marker positions under the series gid.
- **legend**: entry texts in document order vs plan series order; handle
  glyph color (fill for patches, stroke for lines) vs series color.
- **annotations**: axis label texts and unit strings must appear in the
  panel's axes subtree; declared `yerr` must have error-bar glyphs
  (`err__panel__series`).
- **diagrams**: every node label must appear in the SVG text with exact
  spelling (whitespace-normalized); every plan edge must have a rendered
  path under `edge__i`.

## Tolerance policy

Default: `tol = max(2 % of the panel's y-value span, 1e-9)`, overridable
per plan via `"verify": {"tol_rel": ..., "tol_abs": ...}`. 2 % of span is
far above rendering noise (≈1e-4 of span) and far below any real mapping
error (wrong column, wrong sign, wrong unit). Per-value deviations are
reported; a check fails if ANY value exceeds tolerance.

## Check catalog + repair playbook

| check id | fails when | repair |
|---|---|---|
| `transform_y/x@panel` | <2 numeric ticks fitted | ensure axis has ≥2 numeric ticks; redraw |
| `bar_values@p/s` | recovered bar heights ≠ plan values | **fix the plan**: re-bind `values` to the correct column (the report prints both value vectors; if recovered equals ANOTHER series' expected vector, that column was swapped) |
| `line_values@p/s`, `line_x@p/s` | polyline vertices ≠ plan points | same; also check NaN policy (drawer drops NaN → count mismatch is a plan error, reconcile explicitly) |
| `scatter_values@p/s` | marker positions ≠ plan | as above |
| `legend_order@p` | legend entries ≠ series order | reorder series in plan; never hand-edit SVG |
| `legend_color@p` | handle color ≠ series color | re-render from plan (color drift) |
| `axis_label@p/x,y` | declared label/unit absent | set `x_label/y_label/x_unit/y_unit` in plan |
| `tick_range@p` | data span outside tick span | extend limits / confirm no clipping |
| `errorbar_caps@p/s` | yerr declared, no glyphs | pass `yerr` with `capsize>0` |
| `editable_text` | 0 `<text>` + many paths | `svg.fonttype='none'`; re-export |
| `cjk_tofu` | U+FFFD/□ found, or fonts unconfirmed | install CJK font (Noto Sans CJK SC …) or transliterate; inspect PNG |
| `occlusion` | estimated text-box overlap | shorten labels, rotate ticks, enlarge figure |
| `diagram_labels` | node label missing/misspelled | copy entity names character-exact from source |
| `diagram_edges` | edge path missing | fix from/to node ids |
| `plan_data@p` | plan references unreadable file/column | fix binding; error message lists available columns |
| `svg_parse` | SVG not well-formed | re-run drawer |

Any check may also come back **unverifiable** (glyphs not locatable, e.g.
the SVG was produced by a different tool without gids). That is not a
pass: disclose it in `result.json` `uncertainty` and verify the affected
panel by an independent manual measurement (e.g. measure 2 bars against
the tick grid in the PNG).

## Known limits

- **Log scales**: the affine fit is linear. For log axes, fit in log
  space (take log10 of tick labels before fitting) — currently NOT
  automated; declare `unverifiable` and check manually, or keep the
  figure linear.
- **Stacked bars / twin axes / broken axes**: not modeled; read-back of
  individual segments is not attempted.
- **Heavily post-edited SVGs** (hand-moved glyphs, Inkscape regrouping):
  gid structure may be lost → checks degrade to `unverifiable`. This is
  why the repair loop always edits the PLAN, never the SVG.
- **Text rendering**: the verifier checks that font families are named
  and (if fc-list exists) installed; it cannot rasterize. A final human
  look at the PNG is part of the protocol (step 6 of SKILL.md).
- Tolerance is relative to the value span; a near-flat series (span≈0)
  falls back to `tol_abs`.
