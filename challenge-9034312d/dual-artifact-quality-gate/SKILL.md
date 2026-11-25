---
name: dual-artifact-quality-gate
description: >-
  Use when creating or editing source-bound scientific apparatus figures, mechanism or
  technical-route diagrams, and chart-containing figures that need independently reviewable
  SVG/PNG/PDF deliverables. Separates agent-derived source truth and expected observations
  from parsed artifact observations and agent/human visual review; audits direction,
  numbering, legends, chart values, editable layers, exports, top-level result contracts,
  and source-preserving edit diffs. Especially use for figure03/primary-biological-source
  comparison or existing-figure repair. Structural checks never establish scientific truth.
---

# Dual-artifact quality gate

The deliverable is not merely a drawing. It is a **source-derived expectation**, an
**independently observed artifact**, a **visual review**, and an **auditable contract**
that can disagree with one another. A renderer is only a fixture utility, never the QC
authority. Do not generate expectations from the same IR/scene/specification used to draw,
and do not call agreement between those two sides scientific validation.

## Non-negotiable rules

1. Read the actual `/input/case.json`, `/task.md` (and `/input/task.md` if present), source
   documents, original editable artwork, and actual data tables. Never infer content from a
   filename or domain label. Do not ship prepared official answers.
2. Maintain three separate evidence lanes:
   - `truth_table.json`: facts extracted by the agent from actual sources, with exact
     locator/quote or table cell coordinates;
   - `expected_matrix.json` + `semantic_checklist.json`: expectations written from the task
     and truth table before inspecting the new render;
   - `rendered_observations.json`: parsed from the delivered SVG/CSV by
     `artifact_observer.py`, which does not read the IR, truth table, or expected matrix.
     `visual_review.json` is a separate agent/human record of actual rendered images and
     source comparison.
3. Scripts perform **structural and consistency checks only**. They can show that two
   records disagree, not that a biological mechanism, apparatus, or experimental method is
   scientifically correct. Source support and semantic accuracy require agent review.
4. A failed error gate is nonzero. Never delete a check, alter an observation, or relabel a
   failure as a warning to obtain success. At the repair limit, deliver `partial`, retain
   the failed report, and enumerate every residual error and its impact.
5. Preserve every unaddressed element of an existing source. Prove this with node/attribute
   edit diff plus before/after rendered visual diff; a newly redrawn similar figure is not a
   source-preserving edit.
6. Work in `/app/work`; put **all final artifacts and all reports** in `/app/output`, not only
   in work. Runtime preview PNG/PDF files are deliverables and should really be rendered.

## Dependencies and execution boundary

Core scripts require **Python 3.10+ standard library only**; no installation or network access
is needed. `png_diff.py` supports 8-bit non-interlaced grayscale, gray-alpha, RGB, RGBA, and
palette PNGs; record a limitation or use an available real image tool for other encodings.
PDF extraction (`pdftotext` or an equivalent actual parser) and SVG-to-PNG/PDF exporters are
optional environment tools, not bundled dependencies. Inspect `environment/resources.yaml`
when provided, use the real available versions, and disclose any unavailable exporter. The
fixture previewer is deliberately limited to the synthetic example and is not a production
renderer.

## Timeboxed runtime protocol

Budget: 64 model requests, 900 seconds, **at most two repair rounds after the initial
artifact**. Save a partial checkpoint before detailed drawing and update it after every
round. Prefer an honest complete evidence package over aesthetic iterations.

### 0. Discover, inventory, checkpoint

```bash
export SKILL_DIR=/skills/weekly-skill
mkdir -p /app/work/sources /app/output
python3 "$SKILL_DIR/scripts/contract_audit.py" \
  --case /input/case.json --output-root /app/output \
  --init-result /app/output/result.json \
  --report /app/output/contract_audit.checkpoint.json
```

Record source filename, SHA-256 where practical, version/date, pages/sheets, and the requested
output formats. Copy source text/table extracts to work, retaining page, line, row, and column
locators. For PDFs, use an available real parser (for example `pdftotext -layout`) and inspect
relevant original pages visually; parsed text alone is insufficient for arrows and charts.
The checkpoint uses `status:"partial"`, contains top-level `case_id`, every original
`output_contract` key at top level (null until produced), `sources`, `uncertainties`, and
`change_records`. Never nest contract keys under `outputs` or `artifacts`.

### 1. Extract truth and identify mandatory source comparisons

Create `/app/work/truth_table.json` from the actual sources using
`references/evidence-schemas.md`. Include every required entity, relationship, direction,
step/order, marker, legend/style, chart datum, and requested delivery property. Each fact
needs a stable `truth_id`, kind, subject/predicate/value, source path, precise locator, and
verbatim quote or cell reference. Record ambiguous or absent facts in `uncertainties`; never
invent a connector, value, or biological claim.

**Original figure03 / primary biological source.** When the case names figure03 or a primary
biological source, locate and inspect the original figure03 and the primary biological source,
not only a crop, secondary summary, OCR layer, or redraw. Record exact source identity,
version, figure/caption/method locators, and what the original visual actually shows. Compare
entity labels, connectivity, direction/markers, and numbering against that original in
`visual_review.json`. Missing original access is a residual error for a required comparison,
not an automatic N/A.

**Actual charts.** For every actual chart in scope, compare the plotted categories, series,
values, units, signs, scales, and order with the supplied source CSV/table or original paper
data. The agent must document this comparison in `visual_review.json`; a parse-only match or
literal source quote is not scientific judgement. If only a raster chart exists and no data
are recoverable, state that limits digitization and do not fabricate exact values.

### 2. Write the independent semantic gate before rendering

Create `semantic_checklist.json` and `expected_matrix.json` under work from the task and truth
table only. Use `references/semantic-checklist.md` and `references/evidence-schemas.md`.
The checklist names all ten gates below; each is required or has a source/task-based N/A
reason. The matrix maps expected values to observation paths in the **future** artifact.
Do not read the new SVG, renderer scene, or layout IR while writing expectations.

| Gate | What must be reconciled |
|---|---|
| coverage | Every required source fact and requested visual/export element is represented. |
| source_support | Labels/claims preserve source terminology; abbreviations and uncertainty are disclosed. |
| direction_marker_semantics | From/to semantics, visible arrowhead/marker, line role, branch/return direction. |
| numbering_order | Visible numbering and source sequence, including parallel/return/termination semantics. |
| legend_style | Visible swatch/text/style and target encoding agree; style is not the sole semantic carrier. |
| chart_data_values | SVG chart observations and independently parsed CSV values match source-derived cells. |
| editable_layers | Real SVG groups/layers, visible editable text, stable IDs, and chart marks remain editable. |
| export_validity | Requested files open structurally, nonzero dimensions, correct format and declared geometry. |
| result_contract | Top-level keys, status, paths, sources, uncertainties, and changes satisfy case contract. |
| source_preserving_edit_diff | Only authorized source targets changed; unaddressed IDs/structure/content survived. |

Coverage is checked by truth IDs referenced from matrix rows. For required edge facts, expect
both endpoints and marker semantics. For charts, expect both the artifact value and the
independent CSV observation. Structural absence or mismatch is an error unless the task
explicitly makes it advisory.

### 3. Make or edit the real artifact

Create a layered editable SVG, then requested PNG/PDF exports. Use separate meaningful groups
for background, entities, relationships, annotations, chart, and legend as applicable. Keep
text as text and marks as shapes; do not embed only a raster screenshot. Add the stable
`data-qc-*` attributes specified in `references/observation-contract.md` so an independent
parser can observe visible semantics. These attributes are an observation interface, not a
scientific truth layer.

For an existing-source edit, copy the original to work, modify only authorized targets, and
retain unaddressed IDs, groups, labels, marks, and geometry. Record each old/new value and its
truth/source reason in `change_records`. Do not regenerate the whole drawing merely to make
the diff simple.

### 4. Observe independently and audit exports

```bash
python3 "$SKILL_DIR/scripts/artifact_observer.py" \
  --svg /app/output/figure.svg \
  --csv /app/work/sources/actual_data.csv \
  --output /app/output/rendered_observations.json
python3 "$SKILL_DIR/scripts/export_audit.py" \
  --svg /app/output/figure.svg --png /app/output/figure.png \
  --pdf /app/output/figure.pdf --report /app/output/export_audit.json
```

Pass only actual files; omit unavailable optional formats and disclose them. The observer
falls back to visible SVG text but semantic IDs require the documented attributes. If the
artifact cannot be parsed, that is an observation error, not permission to manually overwrite
observed values. Multiple CSVs may be passed with repeated `--csv` options.

### 5. Perform genuine visual and source review

Inspect the actual rendered PNG/PDF, not only XML. For new work, compare to original sources;
for edits, inspect before and after at comparable size. Record reviewer (`agent` or `human`),
time/round, images inspected, source comparisons, pass/fail per relevant gate, and residual
visual defects in `visual_review.json`. Check clipping, font substitution, arrow visibility,
z-order, label placement, legends, and chart readability as well as source meaning. A visual
review record cannot be filled by the QC script in a real case.

Generate pixel evidence when an exporter and PNG tools permit:

```bash
python3 "$SKILL_DIR/scripts/png_diff.py" \
  --before /app/work/before.png --after /app/output/figure.png \
  --diff /app/output/visual_diff.png --report /app/output/visual_diff.json \
  --before-review /app/work/visual_review.before.json \
  --after-review /app/output/visual_review.json
```

Pixel difference shows change, not improvement. Improvement must be supported by resolved
source-backed defects in the two review records. Equal images cannot support an edit claim.

For an existing-source SVG edit, also run:

```bash
python3 "$SKILL_DIR/scripts/edit_diff.py" \
  --before /app/work/original.svg --after /app/output/figure.svg \
  --intent /app/work/edit_intent.json \
  --report /app/output/source_edit_diff.json
```

See `references/review-and-repair.md` for review evidence and `edit_intent.json` rules.

### 6. Reconcile, audit result, and repair at most twice

```bash
python3 "$SKILL_DIR/scripts/semantic_gate.py" \
  --checklist /app/work/semantic_checklist.json \
  --truth /app/work/truth_table.json \
  --matrix /app/work/expected_matrix.json \
  --observations /app/output/rendered_observations.json \
  --visual-review /app/output/visual_review.json \
  --visual-diff /app/output/visual_diff.json \
  --export-report /app/output/export_audit.json \
  --contract-report /app/output/contract_audit.json \
  --edit-diff /app/output/source_edit_diff.json \
  --report /app/output/qc_report.json
```

The command exits 2 on any error. Repair only the source-backed defect, preserve unrelated
source structure, re-render, **rerun the independent observer**, and repeat visual review.
Keep round reports (`qc_report.round1.json`, etc.) and residual defects. Never use two
revisions of the same renderer output as independent evidence of source correctness.

Finalize `result.json`, then audit and rerun the gate once if its contents changed:

```bash
python3 "$SKILL_DIR/scripts/contract_audit.py" \
  --case /input/case.json --result /app/output/result.json \
  --output-root /app/output --report /app/output/contract_audit.json
```

Use final `status:"success"` only when every required gate and required agent visual review
passes and no residual error remains. Use `partial` when a useful artifact exists but errors
or unavailable required evidence remain; use `failed` when no usable requested artifact was
produced. Put residual error code, evidence, affected gate, and practical impact in
`uncertainties`. A script return of zero means structural consistency of the supplied evidence,
not scientific endorsement.

## Output package

Use contract keys exactly as supplied; commonly deliver `figure.svg`, requested PNG/PDF,
`truth_table.json`, `semantic_checklist.json`, `expected_matrix.json`,
`rendered_observations.json`, `visual_review.json`, `visual_diff.json` and previews for edits,
`source_edit_diff.json` for edits, `export_audit.json`, `contract_audit.json`, `qc_report.json`,
and `result.json`. Keep all final reports in output. `sources` identifies real sources;
`change_records` identifies every intentional edit; `uncertainties` includes limitations and
residual defects. No claims of benchmark score, human approval, or scientific validity without
actual evidence.

## Synthetic demonstration and tests

The included example is entirely **SYNTHETIC**, uses invented FEED/PUMP/REACTOR labels and
invented chart values, and is not an official case or answer. It deliberately starts with a
wrong label, reversed direction, and wrong chart value, then makes only authorized corrections
and passes the final consistency gate. The before/after records report actual changes; they
do not claim that a pixel diff proves scientific improvement.

```bash
python3 scripts/run_example.py --example-dir examples/synthetic \
  --output-dir /tmp/dual-gate-example --preview-png /tmp/dual-gate-example/preview.png
python3 scripts/self_test.py
```

See `references/evidence-schemas.md`, `references/observation-contract.md`, and
`references/review-and-repair.md` for schemas, failure handling, and the distinction between
structural consistency and scientific review.
