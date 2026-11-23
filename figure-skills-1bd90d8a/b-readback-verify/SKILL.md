---
name: fig-readback-verifier
description: >
  科研数据图表生成与编辑技能：用 matplotlib 绘制科研绘图/数据图表（柱状图、折线图、散点图）与
  生物学机制示意图/流程图，并通过独立的"回读校验"（draw → read-back → verify → repair 闭环）
  从已保存 SVG 的字形几何中恢复数值、与源数据表逐项比对，做标注校验（轴标签/单位/图例↔系列
  一致性/误差棒/CJK 缺字），保证可编辑源文件（SVG 文本不转曲）与导出格式合规（PNG 300dpi、
  PDF 页面尺寸）。触发条件：需要根据论文 PDF 或 CSV/TSV/JSON 源数据生成科学图表；需要重绘
  Nature/Science 风格的数据图；需要对既有图做保源编辑（source-preserving edit）；需要交付
  可编辑 SVG + PNG + PDF 且数字必须与源数据一致；需要生物学机制/通路示意图（figure03 类）。
  当任务要求"图表中的数值必须可追溯到源数据"或"图示实体名称必须与论文一致"时尤其适用。
---

# fig-readback-verifier

Draw → **read back** → verify → repair. A closed loop for scientific figures.

## Loop invariant

**No figure ships until read-back verification passes or its failure is
explicitly disclosed in result.json.** "画得漂亮但数字错" is a delivery
failure; the verifier catches it mechanically, not by eye.

## Inputs and budgets

- `/input/case.json` — case spec (copy `case_id` **verbatim**; honor every
  field named by `output_contract`).
- `/input/task.md` — the human task description. Read it fully first.
- Material files next to them: paper PDFs (**real PDFs, possibly without a
  text layer**) and/or source data (CSV/TSV/JSON). **Read the real files.
  Never assume content from labels or filenames.**
- Work under `/app/work`; deliver under `/app/output`.
- Budgets: 64 model requests, 900 s wall, 16384 tokens/response. Therefore:
  **save an honest PARTIAL `result.json` within the first minutes**, then
  improve incrementally (see step 0).
- Tools: scientific-python (python3 + numpy + matplotlib), pdftotext,
  pdftoppm, ocr-tool, latex-compiler, office-renderer (soffice — may be
  absent), browser-automation, font-discovery (fc-list — may be absent).

`$SKILL_DIR` below = the directory containing this SKILL.md
(e.g. `/skills/weekly-skill`).

## Pipeline

### 0. Intake + immediate partial result

```bash
mkdir -p /app/work /app/output
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
    --out /app/output/result.json --status partial \
    --note "intake: placeholder result saved before any drawing"
```

Do this FIRST, before any expensive step. Update it after every milestone
with `--note` (each call appends a timestamped `change_record` entry and
never clobbers already-filled contract fields).

### 1. Source extraction (grounding)

- Text PDF: `pdftotext -layout /input/<paper>.pdf /app/work/paper.txt`
- Scanned PDF (no text layer): render pages then OCR:
  `pdftoppm -r 300 -png /input/<paper>.pdf /app/work/page` then run the
  available ocr-tool on `/app/work/page-*.png`.
- Data files: read with the script below or `python3` (csv/json). Note
  exact delimiters, headers, units, NaN cells.
- Write `/app/work/extraction_notes.md`: every number or entity name you
  will use, each with a **locator**: `file#column#row` for tables,
  `pdf#page#N table/figure/paragraph` for papers. If you cannot find a
  value in the sources, do not invent it — mark it uncertain.

### 2. Author `/app/work/figure_plan.json`

A small JSON plan: chart type (`bar`/`line`/`scatter`), series bound to
data-file columns (or literal values **with `source_locator`**), axis
labels + units, style preset, output size; or `mode: "diagram"` with
nodes/edges for mechanism figures (figure03-type). Full field reference:
`$SKILL_DIR/references/plan_authoring.md`. Entity names for diagrams must
be copied **character-for-character** from the sources.

For **source-preserving edits** of an existing figure: first reconstruct
the existing figure's data/structure into a plan (read its values from the
source data or the figure itself), apply only the requested change in the
plan, then draw fresh. Record every change in `change_record`.

### 3. Draw

```bash
python3 $SKILL_DIR/scripts/draw_figure.py /app/work/figure_plan.json \
    --out /app/output/figure --formats svg,png,pdf
```

matplotlib Agg; `svg.fonttype='none'` (text stays editable), PNG 300 dpi,
semantic gids on every data glyph. Writes `/app/work/draw_log.json`
(plan hash, files, font used, warnings incl. `cjk_font_missing`,
series order). Exit 2 + stderr message on plan/data errors — fix the plan.

### 4. Verify (the differentiator)

```bash
python3 $SKILL_DIR/scripts/readback_verify.py \
    --svg /app/output/figure.svg --plan /app/work/figure_plan.json \
    --report /app/output/verify_report.json
```

Pure-stdlib independent pass: parses the SVG, fits the pixel→data affine
transform from axis tick marks, recovers values from glyph GEOMETRY, and
compares against the plan/source data within tolerance (default 2 % of
y-range). Also checks legend↔series order+color, axis labels/units, tick
coverage, error-bar glyphs, CJK tofu, text-editability, label occlusion;
in diagram mode it checks exact entity spelling and edge rendering.
Methodology: `$SKILL_DIR/references/verification.md`. Always exits 0;
read the JSON.

### 5. Repair loop (max 3 rounds)

If `verify_report.json` has `fail` checks:

1. Read each check's `repair` directive (action / target / suggestion).
2. Fix the **PLAN** (or the draw call) — never hand-edit the SVG.
3. Re-draw, re-verify. Save each round:
   `cp /app/output/verify_report.json /app/output/verify_report_roundN.json`
4. If still failing after 3 rounds: ship the best figure but disclose —
   set `status: "partial"`, list the failing check ids and details in
   `uncertainty`, and keep all round reports.

### 6. Export compliance

```bash
python3 $SKILL_DIR/scripts/export_check.py \
    /app/output/figure.svg /app/output/figure.png /app/output/figure.pdf \
    --report /app/output/export_report.json
```

Checks PNG dpi ≥ 300 (pHYs), PDF MediaBox size/pages, SVG
width/height/viewBox + real `<text>` + font fallback list. Fix and
re-export on `fail`. Also open the PNG yourself and LOOK at it once
(occlusion, tofu, legend placement) — the verifier is necessary, not
sufficient.

### 7. Finalize result.json

```bash
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
    --out /app/output/result.json --status complete \
    --uncertainty "<residual doubts, or 'none'>" \
    --note "final: verify=<overall>, export=<status>, rounds=<N>"
```

Fill every `output_contract` field with real content (paths, reports,
edit logs), list `sources` with locators, keep the verification history
in `change_record`.

## What the verifier catches

- **Wrong column mapping** — series bound to the wrong CSV column:
  recovered glyph values ≠ plan values; repair directive names the
  mismatching series and both value sets.
- **Swapped series / legend** — legend order or handle color ≠ series.
- **Unit / magnitude mistakes** — values off by a constant factor
  (e.g. % vs fraction) exceed tolerance and fail read-back.
- **Missing axis labels or units** — declared label/unit absent from SVG.
- **CJK tofu** — U+FFFD/□ glyphs; unconfirmed font families when fc-list
  is absent (warn) so you inspect the PNG.
- **Tick-range clipping** — data span exceeds tick span.
- **Error bars missing** — `yerr` declared but no error-bar glyphs.
- **Text-as-outlines** — SVG with zero `<text>` elements (not editable).
- **Label occlusion** — bounding-box overlap heuristic (warn).
- **Diagram spelling** — any node label not found character-exact in the
  rendered SVG; any edge not rendered.

## Budget / failure protocol

- Save partial `result.json` immediately (step 0). Update it at every
  milestone; never end without a result.json.
- One figure = draw+verify ≈ a few seconds; you have budget for 3 repair
  rounds per figure. Do not start a 4th; disclose instead.
- Missing data column → drawer exits 2 with a message; fix the plan,
  don't patch the data.
- NaN cells → drawer omits those points with a `nan_gap` warning; the
  verifier treats them as expected gaps. Disclose in `uncertainty` if
  gaps are scientifically meaningful.
- soffice/fc-list absent → skip those optional paths; the scripts degrade
  gracefully (warn, not crash).
- **Honesty:** never fabricate scientific data, tool outputs, or
  verification results. Illustrative/synthetic content must be labeled
  示例/example. Partial results must name their limits.
