---
name: fig-edit-workorder
description: >-
  Layered-SVG scientific figure generation AND source-preserving figure editing
  via declarative edit workorders with journal export presets. Trigger for
  tasks involving 科研绘图 / 图表编辑 / 可编辑源文件 / SVG / 期刊模板 / 导出 /
  修改记录: composing charts bound to real source data (CSV/TSV/JSON), building
  mechanism/schematic figures grounded in a paper PDF, or editing an existing
  figure while preserving its linkage to source data. Every figure is a
  semantically-layered SVG (stable ids: axes, series/<name>, annotation/<id>,
  legend) plus a figmap.json sidecar recording the data↔pixel transform and
  element bindings; all edits are a JSON workorder applied by a deterministic
  engine that re-derives geometry from source values (never hand-computed
  pixels), REJECTS value changes without a source_ref, and appends old/new/
  source_ref to change_log.json. Export is preset-driven (Nature/Science
  widths in mm, DPI, font floors, editable text) with a compliance report.
  Use whenever a deliverable must include an editable SVG source, PNG/PDF
  exports, and an auditable 修改记录 / provenance trail.
---

# fig-edit-workorder

Figures are engineering artifacts: a **layered SVG** (text never outlined) +
a **figmap.json** data binding. All changes — restyle, relabel, correct a
value, adapt to a journal — are **declarative workorder ops** applied by a
deterministic engine and appended to **change_log.json**. This turns 改图 from
untraceable hand-editing into an auditable, replayable operation log.

## Inputs and budgets

- `/input/case.json`, `/input/task.md`, material files (paper PDF **without**
  pre-extracted text layer, source data CSV/TSV/JSON, and for edit tasks an
  EXISTING figure file). **READ the real files; never assume content from
  filenames or labels.**
- Work under `/app/work`; deliverables under `/app/output`: editable layered
  `figure.svg`, `figure.png`, `figure.pdf`, and `result.json`.
- Budgets: 64 model requests, 900 s, 16384 tokens/response. **Save an honest
  PARTIAL result.json within the first minutes, then improve incrementally.**

## Two entry modes

- **GENERATE** — no existing figure: compose a new layered figure from source
  data (chart mode) or from the paper's described mechanism (diagram mode).
- **EDIT** — an existing figure file is provided: layerize it, then apply
  workorders. If it has no data binding, value ops are honestly marked
  `unbound — manual confirmation required`.

## Pipeline (exact commands)

Let `SKILL_DIR=/skills/weekly-skill` (the install location).

**0. Intake + immediate partial result (do this FIRST, before heavy work):**

```bash
mkdir -p /app/work /app/output
cat /input/case.json /input/task.md
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status partial \
  --note "intake complete; pipeline started"
```

**1. Source extraction — read the REAL materials:**

```bash
pdftotext -layout /input/<paper>.pdf /app/work/paper.txt   # if a PDF is given
# fallbacks for scanned PDFs: pdftoppm -r 200 -png paper.pdf /app/work/pg
# then ocr-tool on the page images
head -50 /input/<data>.csv                                  # data files
```

Record extraction notes with locators (`paper.pdf#page=3,fig2`,
`data.csv#column=rate,row=4`) — these become `source_ref`s and `sources` in
result.json. Handle exceptions honestly: missing columns, NaN cells, scale
anomalies, overlong labels (wrap/rotate), missing CJK fonts (the composer
warns; keep labels editable), empty series.

**2a. GENERATE mode** — author a small compose plan JSON (chart types
bar/line/scatter with optional yerr; `diagram` mode with nodes/edges for
mechanism figures; every series bound to data columns or literal values with
`source_locator`; labels + units), then:

```bash
python3 $SKILL_DIR/scripts/compose_svg.py /app/work/plan.json \
  --out-svg /app/work/figure.svg --figmap /app/work/figmap.json
```

Compose at the TARGET venue width (`width_mm`) so font sizes survive export.

**2b. EDIT mode** — normalize the existing figure (never rasterizes):

```bash
python3 $SKILL_DIR/scripts/layerize_svg.py /input/<figure>.svg \
  --out-svg /app/work/figure.svg --layer-map /app/work/layer_map.json
```

Check `layer_map.json`: `editable:false` (all-outlined text or raster-only)
must be reported as a limitation. No figmap exists for external figures →
value ops will fail as unbound unless you reconstruct a figmap or the case
only needs style/label ops.

**3. Author `/app/work/workorder.json`** (op schema:
`references/workorder_schema.md`) and apply:

```bash
python3 $SKILL_DIR/scripts/apply_workorder.py /app/work/figure.svg \
  /app/work/workorder.json --figmap /app/work/figmap.json \
  --out-svg /app/output/figure.svg --log /app/output/change_log.json
```

(For EDIT-mode cases keep the input as the layerized file and omit `--figmap`
if none exists.) Read the per-op stdout: every `rejected`/`failed` op needs a
decision — fix the op or record the limitation.

**4. Export to the target venue** (presets in
`presets/journal_presets.json`; use `--preset generic` when the case names no
venue; `nature_double` shown as example):

```bash
python3 $SKILL_DIR/scripts/export_journal.py /app/output/figure.svg \
  --preset nature_double --out-dir /app/output \
  --report /app/output/export_report.json
```

PDF via `soffice`, PNG at preset dpi via `pdftoppm -r <dpi>` from that PDF.
If soffice is absent the script degrades gracefully to
`renderer_unavailable` (exit 0) — then produce the PNG preview by any
available route (e.g. matplotlib re-render from the same plan, or
`pdftoppm` from a latex-compiler PDF) and state the deviation honestly.

**5. Compliance check:**

```bash
python3 $SKILL_DIR/scripts/export_check.py /app/output/figure.svg \
  /app/output/figure.pdf /app/output/figure.png \
  --preset nature_double --report /app/output/export_check.json
```

**6. Self-check vs the six scoring checkpoints, then finalize:**

- 科学实体 — every plotted value traces to a source locator; mechanism nodes
  trace to paper passages.
- 空间关系 — layout matches the source (ordering, grouping, arrow direction).
- 数据编码 — bar heights/point positions equal figmap predictions.
- 图例标注 — legend, axis titles with units, tick labels, annotations present.
- 可编辑源文件 — SVG has semantic layer ids and real `<text>` (not outlines).
- 导出格式 — export_check.json has no `fail`; warnings explained in result.json.

```bash
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status complete \
  --sources "paper.pdf#page=3,fig2,data.csv#column=rate" \
  --uncertainty "yerr column absent; error bars omitted" \
  --change-record /app/output/change_log.json --note "final"
```

`result.json` must contain the original `case_id` verbatim, every field named
by the case `output_contract`, honest `status` (complete/partial/failed),
`sources`, `uncertainty`, and `change_record`.

## Budget / failure protocol

- Minute 0–2: steps 0–1 done, partial result.json saved. Never skip this.
- Each pipeline stage writes its own artifact; a later failure never loses
  earlier work. On any tool failure: read stderr, apply the documented
  fallback, and record the deviation in result.json + export_report.json.
- If time runs short: ensure /app/output holds the best SVG + whatever
  exports exist + result.json with status "partial" naming exactly what is
  missing. A honest partial beats a polished claim.
- 16384-token responses: write files with heredocs/scripts, not giant inline
  dumps; re-run scripts instead of hand-editing outputs.

## Honesty rules (non-negotiable)

- Never fabricate data, tool outputs, or provenance. Every value-bearing edit
  needs a `source_ref`; manual edits are allowed only with `manual:true` +
  `reason` and are conspicuously logged as 人工修改.
- Partial results name their limits (`uncertainty`, `notes`).
- Illustrative content is labeled 示例/example. The worked example in
  `examples/minimal_example.md` uses synthetic data — never copy its values
  into a real case.

## References

- `references/workorder_schema.md` — all ops, fields, rejection rules,
  figmap format, provenance discipline.
- `references/journal_presets.md` — preset table, export parameter meaning,
  how to add a venue.
- `examples/minimal_example.md` — full worked 示例: CSV → compose →
  4-op workorder (+1 rejected) → change_log → export → check.
- `README.md` — install, dependencies, file map, limitations.
