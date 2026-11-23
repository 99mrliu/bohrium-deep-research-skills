---
name: fig-spec-compiler
description: >
  Declarative-spec compiler for scientific figure generation and source-preserving
  figure editing (科研绘图 / 数据图表 / 示意图 / 机制图 / 流程图 / 图表编辑). Trigger whenever
  a task asks to generate a chart bound to real source data (CSV/TSV/JSON), draw a
  biological schematic/mechanism/flow figure grounded in a paper PDF, or edit an
  existing figure while preserving its sources — and the deliverables must include a
  layered editable SVG (可编辑源文件), PNG/PDF exports, and verifiable glyph-to-source
  provenance. The agent does the intellectual work (read the paper/data, decide
  encodings, units, entity names) and hand-writes ONE declarative artifact,
  figure.spec.json; a deterministic, zero-dependency compiler (Python 3 stdlib only)
  then does ALL mechanical drawing, stamps every glyph with a data-src provenance
  attribute, and emits mapping_ledger.json with the bidirectional glyph↔source-cell
  correspondence. Handles missing columns, NaN/empty cells, magnitude anomalies,
  overlong labels, missing CJK fonts and absent renderers explicitly and honestly.
---

# fig-spec-compiler

## Purpose and division of labor

You (the agent) do the science: read the actual input files, extract entities,
values and relations **with their locators**, choose chart type / encodings /
units / scales, and write **one** hand-authored artifact: `/app/work/figure.spec.json`.

The compiler (`scripts/compile_figure.py`, Python 3 stdlib only, no matplotlib,
no numpy) does **all** mechanical drawing: layout engine, nice-number ticks,
grouped bars / polylines / markers / error bars, diagram nodes/edges/compartments,
label wrapping and rotation, legend, layered SVG output with `data-src`
provenance on every glyph, plus `mapping_ledger.json` (glyph ↔ source cell,
both directions). **Never hand-edit the SVG.** If the figure is wrong, fix the
SPEC and recompile. For a *source-preserving edit* case: extract the original
figure's values/entities/relations into a spec that reproduces them, apply the
requested change in the spec, recompile; record every change in `change_record`.

`$SKILL_DIR` below = the installed skill directory (`/skills/weekly-skill` at
evaluation time). All scripts are stdlib-only and safe to re-run.

## Inputs and budgets

- `/input/case.json`, `/input/task.md`, material files (real PDF **without** a
  pre-extracted text layer, and/or CSV/TSV/JSON data). READ the real files;
  never assume content from labels or filenames.
- `environment/resources.yaml` lists provided tools (check it if a tool seems
  missing).
- Budgets: 64 model requests, 900 s wall clock, 16384 tokens/response.
- Work under `/app/work`; deliverables under `/app/output`:
  `figure.svg` (editable layered source), `figure.png`, `figure.pdf`,
  `mapping_ledger.json`, `export_manifest.json`, `result.json`.

## Pipeline (numbered steps; run in order)

### 0. Intake + immediate partial result (first minutes, non-negotiable)

```bash
mkdir -p /app/work /app/output
cat /input/case.json; cat /input/task.md
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status partial \
  --note "intake: scaffold created, extraction in progress"
```

This guarantees an honest partial `result.json` (case_id verbatim, every
`output_contract` field present) exists from the first minutes onward.

### 1. Source extraction (evidence first)

```bash
pdftotext -layout /input/<paper>.pdf /app/work/paper.txt
# if a table/figure region is ambiguous in the text layer:
pdftoppm -png -r 100 -f <page> -l <page> /input/<paper>.pdf /app/work/page
# still unreadable (scanned)? use ocr-tool if provided in resources.yaml
```

- Read data files directly (`head`, or python3 csv/json). Note delimiter,
  header row, units, missing-value tokens.
- Write `/app/work/extraction_notes.md`: every entity name (copied **verbatim**
  — genes/proteins/species/compounds), every value **with its locator**
  (`data.csv#column=value,row=3` or `paper.pdf#page=4,table=2,line=…`),
  every relation (activates/inhibits/binds) with its locator.
- **Never invent values.** If a needed value is missing/illegible, plan to mark
  it `"uncertain": true` in the spec instead of guessing.

### 2. Hand-author the spec (the ONLY hand-written artifact)

Write `/app/work/figure.spec.json` following `$SKILL_DIR/references/spec_authoring.md`
and the schema `$SKILL_DIR/spec_schema.json`. Mode `chart` for source_value_chart
cases; mode `diagram` for figure03-style schematic/mechanism/flow cases. Every
data-bearing element needs `data.source`, `source_locator`, `derived` or
`manual: true`.

### 3. Validate

```bash
python3 $SKILL_DIR/scripts/validate_spec.py /app/work/figure.spec.json \
  --report /app/work/validate_report.json
```

Fix all errors. Warnings (label length, unit inconsistency, magnitude span,
missing `error_meaning`, CJK risk) must be fixed or **consciously** accepted —
record accepted ones in `result.json` uncertainty.

### 4. Compile

```bash
python3 $SKILL_DIR/scripts/compile_figure.py /app/work/figure.spec.json \
  --out-svg /app/output/figure.svg --ledger /app/output/mapping_ledger.json
```

Exit 2 with a clear message means a spec/data problem (e.g. missing column) —
fix the locator in the SPEC, never the data, never the SVG.

### 5. Export previews

```bash
python3 $SKILL_DIR/scripts/export_preview.py /app/output/figure.svg \
  --out-dir /app/output --manifest /app/output/export_manifest.json
```

Chain: soffice → PDF, then pdftoppm -r 300 → PNG (fallback: soffice direct
PNG). If no renderer exists the script still exits 0 with
`status: renderer_unavailable` — disclose that in `result.json` and deliver the
SVG as the authoritative source. **Inspect the PNG yourself**: tofu boxes,
occluded labels, legend/series mismatch are all visible there.

### 6. Self-check against the six checkpoints (fix the SPEC, recompile)

| Checkpoint | What to verify (in PNG + ledger) |
|---|---|
| 科学实体 | names spelled exactly as in source (compare against extraction notes) |
| 空间关系 | layout/spatial relations match the task (arrows, compartments, panels) |
| 数据编码 | bar heights / point positions ↔ values (ledger transform strings let you recompute) |
| 图例标注 | axis labels + units + magnitude, legend ↔ series, error-bar meaning declared |
| 可编辑源文件 | layered `<g id="layer-…">`, text stays `<text>` (no outlines), opens in editors |
| 导出格式 | PDF/PNG produced, size/dpi sane, no tofu, manifest status ok |

Also walk the exception list: missing column handled, NaN drawn as gap + ledger
note, scale/magnitude sane, overlong labels wrapped/rotated/truncated, CJK
fallback recorded, export deviations disclosed, no label occlusion.

### 7. Finalize result.json

```bash
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status complete \
  --source "paper.pdf#page=4,table=2" --source "data.csv#columns=group,value" \
  --uncertainty "<anything unresolved, else omit>" \
  --note "final: <what was drawn, what was verified>"
```

Fill each `output_contract` field with the real deliverable content (paths,
summaries). Use `--status partial` when anything required is missing, and say
exactly what and why in the note + uncertainty.

## Time checkpoints

- **t ≈ 0–60 s:** steps 0–1 done; partial result.json saved.
- **t > 600 s elapsed:** stop refining; jump to step 7 and finalize an honest
  partial with whatever is verified so far. A complete honest partial beats a
  crashed perfect plan.
- Near the request budget: prefer fewer, larger tool calls; the compiler is
  deterministic so re-runs are cheap and safe.

## Failure handling (each is scored — handle explicitly)

- **Missing column / file** → compiler exits 2 naming the available columns;
  correct the locator in the spec.
- **NaN / empty / non-numeric cell** → compiler draws a gap (bar absent, line
  broken) and records `missing_value` in the ledger; verify the gap is
  intentional, never silently averaged away.
- **Scale / magnitude anomaly** (span > 1e6) → validator warns; choose
  `"scale": "log"` or restate the unit explicitly (e.g. "10^3 cells"); never
  rescale without saying so on the axis.
- **Overlong labels** → validator warns > 60 chars; node/annotation text is
  wrapped, crowded x tick labels are rotated −40°, and still-overlong category
  labels are truncated with "…" plus a ledger warning. Prefer shortening in
  the spec.
- **Missing CJK font (tofu risk)** → SVG carries a font-family fallback stack;
  export_manifest reports fc-list findings; if the PNG shows tofu, record it
  in uncertainty and keep labels English if the task allows.
- **Export failure / no renderer** → export_preview exits 0 with
  `renderer_unavailable`; disclose in result.json; SVG + ledger remain the
  verifiable deliverables.
- **Label occlusion** → inspect the PNG; move the annotation/legend in the spec
  (legend.position, annotation x/y/anchor) and recompile.
- **Illegible PDF region** → try pdftoppm zoom / ocr-tool; if still unreadable,
  mark the element `uncertain: true` (rendered dashed, recorded in ledger) and
  disclose — do not guess.

## Honesty rules

Never fabricate scientific data or tool outputs. A partial result must name its
limits. Anything illustrative must be labeled 示例/example. Timestamps appear
only in the ledger/manifest/result records — the SVG itself is deterministic
(same spec + same data ⇒ byte-identical SVG), so reviewers can re-run and
compare.

See also: `references/output_contract.md` (result.json contract + budget
protocol), `references/spec_authoring.md` (authoring guide),
`examples/minimal_example.md` (complete worked 示例 for both modes).
