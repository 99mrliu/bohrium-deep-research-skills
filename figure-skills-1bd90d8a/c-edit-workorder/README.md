# fig-edit-workorder

**Version 1.0.0.** A skill for auditable scientific-figure generation and
editing: figures live as semantically-layered SVG with a `figmap.json`
data↔pixel binding; all modifications are declarative JSON **workorders**
applied by a deterministic engine; every op is logged with
old/new/source_ref; export is preset-driven (journal width in mm, DPI, font
floors, editable text) with a compliance report.

## What it does

- **GENERATE**: compose bar/line/scatter charts (grouped, with yerr) or
  node/edge mechanism diagrams from a small plan JSON, bound to real source
  data columns with locators.
- **EDIT**: layerize an existing SVG (semantic ids, heuristic layers, never
  rasterizes), then apply workorders. Without a figmap, value ops fail
  honestly as `unbound — manual confirmation required`.
- **Workorder engine**: `update_value` re-derives bar/line/scatter geometry
  from the bound value through the figmap transform — verified to exact
  pixels — and is **rejected** without `source_ref` unless marked
  `manual:true` + `reason` (logged as 人工修改). Plus `restyle_series`,
  `relabel`, `move_annotation`, `add_annotation`, `set_axis_range`
  (re-fits transform, rescales all bound glyphs, rewrites ticks),
  `highlight_region`.
- **Export**: rescale to venue width (viewBox untouched → lossless), PDF via
  soffice, PNG at preset DPI via pdftoppm, font-floor scan, CJK font
  inventory — with graceful `renderer_unavailable` degradation (exit 0).
- **Compliance**: width vs preset (±1 mm), PNG pHYs dpi, PDF MediaBox,
  editable `<text>`, font-family fallbacks, font floor at final scale,
  background policy.
- **Provenance**: change_log.json (seq/ts/op/target/old/new/source_ref/
  status) is a first-class deliverable; result.json helper guarantees the
  output_contract fields with honest pending placeholders.

## Install

Copy this directory to `/skills/weekly-skill` (or set `SKILL_DIR` to its
path). No build step.

## Dependencies

| tool | needed by | if absent |
|------|-----------|-----------|
| python3 ≥ 3.8 | everything | — |
| matplotlib + numpy | `scripts/compose_svg.py` only | compose unavailable; EDIT/layerize/workorder/export/check still work (pure stdlib) |
| soffice (LibreOffice) | PDF/PNG render in `export_journal.py` | `renderer_unavailable` status, exit 0, SVG still written |
| pdftoppm / pdftotext (poppler) | PNG@dpi from PDF / PDF text extraction | PNG skipped with deviation note / use ocr-tool route |
| fc-list (fontconfig) | system font inventory in export report | inventory skipped with deviation note |

Python packages beyond matplotlib+numpy: **none** (workorder engine,
layerize, export, check, result are stdlib-only).

## Usage (quick tour)

```bash
SKILL_DIR=/skills/weekly-skill
# 0. partial result first
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status partial --note "started"
# 2a. GENERATE
python3 $SKILL_DIR/scripts/compose_svg.py plan.json \
  --out-svg /app/work/figure.svg --figmap /app/work/figmap.json
# 2b. or EDIT
python3 $SKILL_DIR/scripts/layerize_svg.py existing.svg \
  --out-svg /app/work/figure.svg --layer-map /app/work/layer_map.json
# 3. apply workorder
python3 $SKILL_DIR/scripts/apply_workorder.py /app/work/figure.svg \
  workorder.json --figmap /app/work/figmap.json \
  --out-svg /app/output/figure.svg --log /app/output/change_log.json
# 4-5. export + check
python3 $SKILL_DIR/scripts/export_journal.py /app/output/figure.svg \
  --preset nature_double --out-dir /app/output \
  --report /app/output/export_report.json
python3 $SKILL_DIR/scripts/export_check.py /app/output/figure.svg \
  /app/output/figure.pdf /app/output/figure.png \
  --preset nature_double --report /app/output/export_check.json
# 6. finalize
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status complete \
  --sources "data.csv#column=rate" --change-record /app/output/change_log.json
```

See `SKILL.md` for the full harness-oriented pipeline and
`examples/minimal_example.md` for a complete worked 示例.

## File map

```
SKILL.md                      entry instructions (frontmatter: name/description)
README.md                     this file
GITHUB_URL.txt                source repository pointer
presets/journal_presets.json  generic / nature / science / presentation presets
scripts/compose_svg.py        matplotlib composer + figmap writer (needs mpl)
scripts/layerize_svg.py       external SVG -> semantic layers (stdlib)
scripts/apply_workorder.py    workorder engine + change log (stdlib)
scripts/export_journal.py     preset-driven PDF/PNG export (stdlib)
scripts/export_check.py       compliance checker (stdlib)
scripts/make_result.py        result.json create/update (stdlib)
references/workorder_schema.md  op schema, rejection rules, figmap format
references/journal_presets.md   preset table, parameter guide, custom presets
examples/minimal_example.md     worked illustrative 示例
```

## Limitations (honest list)

- `update_value` does **not** re-derive error-bar (yerr) geometry; the log
  entry warns. Re-compose when error bars must move.
- Scatter marker *shape* restyle unsupported (glyphs live in `<defs>`); color
  works.
- `set_axis_range` on x requires a linear axis; bar charts on linear x cannot
  be x-rescaled (category-x bars rescale fine on y).
- Tick rewriting keeps the existing tick count with evenly spaced values.
- Without soffice, PDF/PNG previews cannot be produced by
  `export_journal.py` — it reports `renderer_unavailable` (exit 0) rather
  than fabricating a render.
- layerize heuristics classify by id/class hints then geometry; exotic SVGs
  may land in `layer/artwork-N`. layerize never invents a data binding:
  value ops on external figures stay `unbound` until a figmap exists.
- ET round-trip rewrites attribute order/whitespace and drops the DOCTYPE;
  geometry, ids, styles, and text are preserved.
