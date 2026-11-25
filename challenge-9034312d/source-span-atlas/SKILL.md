---
name: source-span-atlas
description: >-
  上游来源真实性与图稿逐元素溯源。用于从真实论文PDF/方法段、原始生物学Figure 03、实际CSV和既有SVG生成或编辑实验装置图、步骤顺序、材料流向、技术路线及简单数据图。先建立带唯一归一化精确原文跨度、页/节/图定位、源文件哈希、explicit/inferred/unsupported状态、冲突处置、独立语义核对和源—图元覆盖的source-span atlas；门禁通过后再简单分层渲染或做保留原SVG字节的XML定点修改。引文存在绝不等于科学含义正确，必须分别对照实际PDF上下文和原图；绝不补齐“最可能”的连接、回流、支路或步骤。适用于需要可审计、可编辑、可复跑来源图稿的任务，不适用于自由装饰插画、复杂自动布局、统计拟合或无来源臆造机制。
---

# Source-span atlas — upstream source authenticity before rendering

## Non-negotiable scientific boundary

The primary deliverable is **a source-span atlas joined bidirectionally to the editable visual**, not merely a picture. Treat these as separate gates:

1. **Exact source span:** a sufficiently contextual quote occurs uniquely after the declared normalization in exact source bytes, with computed offsets and actual page/line/section/figure locators.
2. **Scientific meaning:** you separately read the actual PDF context and visually inspect the actual original figure/panels, then compare identity, relation type, direction, order, counts, units, scope, and exclusions with each proposed visual.
3. **Visual coverage:** each assertion has exactly one scientific SVG target; every scientific SVG target maps back to an assertion; actual CSV charts retain exact column names, raw values, and source rows.

**Quote presence is never proof that scientific meaning is correct.** A passing script verifies spans, locators, review attestations, CSV rows, and coverage—not scientific truth. The native agent remains responsible for the real semantic comparison.

Do not invent missing connections or use domain plausibility/“best guess” flows. Unsupported assertions and unresolved conflicts fail. Inferred connections are forbidden by the core. If the material is missing, ambiguous, contradictory, or unreadable, deliver supported parts as `partial` and name omissions; never silently harmonize.

Budget: **64 model requests / 900 seconds**, deterministic repeated outputs, and **at most two bounded review rounds**. Spend effort on source authenticity and semantics, not decorative polishing.

## Runtime contract (official cases)

1. Read the **actual** `/input/case.json`. Read actual task text by checking both `/input/task.md` and `/task.md`; do not assume a path before checking. Read `environment/resources.yaml` where provided. Inventory actual files, hashes, readable formats, and task constraints. A filename/domain label is not source content.
2. Copy `case_id` exactly. Copy every key of the case's `output_contract` into final `/app/output/result.json` **at TOP LEVEL**, with actual paths/values required by that contract. Do not nest these fields only under `output_contract`, and do not force the bundled example's keys onto a real case.
3. Work only in `/app/work`. Put every final figure, editable source, export, atlas, report, change record, and `result.json` in `/app/output`. Use `/skills/weekly-skill` for installed Skill resources. Resolve references from the Skill/script location, not current working directory.
4. Immediately write a valid `/app/output/result.json` checkpoint with `case_id`, all contract keys (actual value or explicit null until produced), `status:"partial"`, known `sources`, `uncertainties`, `change_records:[]`, and actual planned artifact paths. Improve it incrementally. At deadline/failure, keep an honest valid `partial`/`failed`; never discard the checkpoint because the gate fails.
5. Final `status` is exactly one of `success`, `partial`, `failed`. Include actual `sources` (file/hash/version/locators), `uncertainties`, `change_records`, `verdict`, real `artifacts`, and export checks. `partial` identifies concrete missing/unfinished items. Never invent model scores, official answers, resources, installed software, scientific data, or an export success.
6. There are **no prepared official answers** in this Skill. `examples/minimal` and `tests/negative` are conspicuously synthetic interface tests only.

## Phase A — acquire and inspect the real upstream sources

### PDF and methods

1. Copy only actual input material to `/app/work`; keep originals unchanged. For a text-layer PDF with preinstalled Poppler:

```bash
python3 /skills/weekly-skill/scripts/extract_pdf_text.py \
  --pdf /input/actual.pdf \
  --output /app/work/sources/actual.txt \
  --report /app/work/sources/actual-extraction.json
```

The helper uses `pdftotext -layout -enc UTF-8`, preserves form feeds, hashes PDF/text, and exits nonzero if missing/empty. It makes no install or OCR claim. If the environment supplies another PDF tool, use that actual tool and record commands/hashes. If scan/OCR is needed, use only an available real tool, disclose OCR uncertainty, and preserve page mapping. Otherwise report missing readable content.

2. Read surrounding methods/caption/abbreviations in the **actual PDF page view**, not just the text extraction. Check tables, superscripts, units, references, and figure panels. Preserve original page evidence: form-feed-derived `page`, optional `printed_page`, section/figure and panel. Do not auto-dehyphenate or fuzzy-correct a quote.
3. Select contextual quotes that uniquely identify one occurrence. A noun co-occurring in a sentence is not automatically an entity relation; prose “connected” does not automatically establish material direction.

### Primary biological source and original Figure 03

1. Identify the primary source from the actual case and inspect the actual original Figure 03 or original PDF page rendering at readable scale. Do not substitute a stylized derived figure, file-label-based guess, or general biological knowledge.
2. Record `inspection_mode:"direct_visual"`, actual source hash, inspected page/panels, source identity/version, and a concrete comparison. Inspect visible labels, arrow tails/heads, split/join/crossing, feedback, line styles, panel identity, units/scales, and absence claims. Never infer a junction from crossing or direction from left/right placement alone.
3. A binary original PNG/PDF is allowed at runtime: use a genuine UTF-8 caption/extraction at source `path` for exact text matching, put original bytes at `visual_path`, and record `visual_sha256`. The review hash must match those exact original visual bytes. A text-native original SVG can itself be `path`, as in the synthetic example.
4. If Figure 03 is missing/unavailable, say so and mark `partial`/`failed`; do not claim direct inspection. If prose and figure disagree, record an unresolved conflict and block contested rendering unless actual context resolves it.

### Actual CSV data

Read the supplied CSV itself. Use exact case-sensitive header names. Confirm units/meaning from methods, preserve raw values and file rows, and define what encodes x/y/category/size/color before drawing. Do not rename a guessed column into apparent success, fit/impute values, infer error bars, or substitute example data. The core's optional chart is only a simple two-numeric-column line/scatter in CSV order; use a native targeted SVG edit for other supported encodings while retaining the same mapping records.

For complete source/atlas field syntax see `references/atlas-schema.md`; for PDF/semantic/figure detail see `references/semantic-and-figure-review.md`.

## Phase B — author the atlas before the figure

Write `/app/work/source_atlas_input.json` based only on actual material. Use schema `source-span-atlas/1.0` and the real case ID/contract.

For every proposed entity, connection, ordered step, stage, data encoding, or scientific note, create an assertion:

- stable assertion `id`, `category`, source-faithful `label`, exactly one `visual.id`;
- `evidence_status`: `explicit`, `inferred`, or `unsupported`;
- unique `evidence[]` entries with `source_id`, exact `quote`, actual `locator.page`, and `section` or `figure`/`panel`;
- separate `semantic_review` with `result:"match"`, actual `reviewed_sources`, reviewer, and a meaning-level comparison;
- for connections, source-reviewed `from`/`to`; for steps, unique positive `order`; for figure evidence, matching `figure_review_id`;
- for `inferred`, a bounded rationale, dashed visual, and retained uncertainty. Never make a connection inferred merely to make the drawing complete.

`unsupported` always fails; do not render it and do not create a factual waiver. A failed report may list it. To obtain a later pass, remove the affirmative assertion and disclose the omission/uncertainty. Inferences must never be represented as direct observations.

Record conflicts explicitly. `status:"unresolved"` blocks. A resolved conflict needs affected assertion/source IDs, a source-grounded explanation, and exact visual treatment. Never decide by prettier source, expected answer, longer prose, or domain intuition. Keep missing connections out; an absence note requires its own source/scope support.

For edits, reverse-build the assertion-to-existing-SVG mapping without changing the original. Important retained scientific visuals also need sources/semantics; do not introduce orphan groups or untraceable factual legends.

## Phase C — validate, checkpoint, and only then render/audit

For new generation:

```bash
python3 /skills/weekly-skill/scripts/source_span_atlas.py \
  --atlas /app/work/source_atlas_input.json \
  --output-dir /app/output
```

This stdlib core:

- hashes/reads actual UTF-8 sources (plus original binary `visual_path` hashes);
- applies per-character NFKC, canonical curly quotes/dashes, and whitespace folding, retaining original-to-normalized offset maps;
- requires a unique exact normalized substring, computed page/lines, and section/figure locator; no fuzzy acceptance;
- separately requires semantic matches and original-figure direct-review links/hashes;
- blocks unsupported claims, inferred connections, missing endpoints, duplicate step orders, unresolved conflicts, bad CSV columns/rows/numbers, and semantic mismatches/unreviewed claims;
- renders only passed assertions into editable layered SVG, or audits an existing edited SVG without rebuilding;
- parses the SVG to verify bidirectional source/assertion/visual coverage;
- writes real `atlas.json`, `report.md`, `figure.svg` (when passed), and contract-aware `result.json`; invalid input exits nonzero and writes failure reports.

Save the first valid partial as soon as possible. If gate errors occur, batch-fix all real spans/locators/semantic mismatches in review round 1. Never change a scientifically correct quote merely to satisfy layout, and never weaken the matcher to force a pass.

Optional previews (each flag is independent and may be used alone or together):

```bash
python3 /skills/weekly-skill/scripts/source_span_atlas.py \
  --atlas /app/work/source_atlas_input.json \
  --output-dir /app/output \
  --preview-png /app/output/figure.png \
  --preview-pdf /app/output/figure.pdf
```

Core dependencies are Python 3 stdlib. Exports honestly detect installed CairoSVG/native Cairo, `rsvg-convert`, Inkscape, or headless Chrome/Chromium; PDF browser detection checks `SOURCE_SPAN_ATLAS_BROWSER`, PATH, and standard installed application locations, with no installs. PNG signature/dimensions and PDF header/EOF/page tree/page object/MediaBox/startxref structure are checked in the actual bytes. Missing or failed exporters retain SVG, record attempts, yield `partial`, and never claim the missing format. Visually inspect actual PNG/PDF: arrow direction, scientific identity, clipping, overlap, fonts/CJK, chart values. Structural PDF checks are not visual or scientific verification. Record actual dimensions/tool/attempts and font risks.

## Phase D — source-preserving SVG edits

For an edit task, **do not call generation mode on the original and label the rebuilt result an edit**. Keep original bytes and only targeted XML changes.

1. Update atlas and independently validate new/changed scientific meaning first. Keep a passed gate report.
2. Create a patch JSON with existing element IDs plus `new_text` and/or existing `attributes`, reasons, and assertion IDs.
3. Apply to a separate output file:

```bash
python3 /skills/weekly-skill/scripts/patch_svg.py \
  --input-svg /app/work/original.svg \
  --patch /app/work/patch.json \
  --gate-report /app/work/first-pass-atlas.json \
  --output-svg /app/output/edited.svg \
  --records /app/output/svg_changes.json
```

The helper locates XML byte ranges using stdlib Expat, preserves all unaffected bytes, refuses input overwrite/missing/duplicate targets and nested-parent replacement, reparses output, and emits original/output SHA-256 plus before/after records. It never serializes a new ElementTree over the source.

4. Merge actual records into atlas `change_records` (including `kept` entries for important untouched elements when reporting them), then audit without rebuilding:

```bash
python3 /skills/weekly-skill/scripts/source_span_atlas.py \
  --atlas /app/work/source_atlas_input_with_changes.json \
  --output-dir /app/output \
  --audit-svg /app/output/edited.svg \
  --preview-png /app/output/edited.png
```

5. Compare original/edited previews. Changed claim, exact before/after, reason, source span, gate verdict, and unchanged-byte verification must agree. If insertion/deletion/complex geometry is required, use a genuinely targeted XML patch with equivalent provenance or return `partial`; do not fabricate a source-preserving claim.

See `references/svg-editing-and-exports.md` for patch limits and export/font preflight.

## Failure handling and two review rounds

| Situation | Required outcome |
|---|---|
| Missing source / unreadable PDF / no original Figure 03 | `partial` or `failed`; explicit `uncertainties`; no reconstruction |
| Quote not found or repeated | Fix exact contextual quote; never fuzzy-pass or choose arbitrary occurrence |
| Quote found but meaning differs/unreviewed | Fail semantic gate; re-read actual context/figure and correct or omit visual |
| Missing connection/order/direction | Omit and disclose; no inferred filler arrow, cycle, waste, pump, or branch |
| Source/figure/source-version conflict | Record; unresolved blocks; resolved needs rationale and visual treatment |
| CSV header/value mismatch | Fail; map actual headers/rows or omit chart, never substitute values |
| Existing SVG edit | Targeted XML patch + before/after + audit; never rebuild-and-call-edit |
| Export/font failure | Keep editable SVG, `partial`, attempts/font uncertainty; no installed-tool claim |
| Dense layout / unsupported renderer operation | Prefer readable partial/native targeted layout; do not shrink until labels overlap |
| Budget pressure | Freeze valid atlas/result/SVG checkpoint, state remaining checks, stop decorative iteration |

- Initial checkpoint: immediately after actual task/contract inventory.
- Review round 1: batch source provenance + actual PDF/figure semantic comparison + CSV + coverage; produce valid figure or honest failed/partial artifacts.
- Review round 2: targeted failed spans, semantic corrections, edit preservation, export/canvas/font checks. Stop after round 2.
- SVG is UTF-8 editable with stable IDs/layers/text. Core uses a font fallback stack and no font embedding; RGB only. Font embedding/CMYK/PDF preflight and fancy autorouting are not claimed. Inspect actual exports rather than assuming.

## Minimal runnable synthetic example and negative test

Use explicit `--example-dir` and `--output-dir`; both are required. The example creates real layered SVG, result/atlas/report, compares deterministic expected core text, and independently checks optional exports requested with `--preview-png` and/or `--preview-pdf`. See `references/usage.md` for exact invocation. The negative wrapper requires an unsupported invented connection to return nonzero, emit `UNSUPPORTED_ASSERTION`, and produce no figure. Do not use either fixture as official case content.

Reusable/maintainable resources: `scripts/atlas_lib.py` (normalization, spans, validation, CSV, layered SVG, coverage), `scripts/source_span_atlas.py` (CLI/export/result), `scripts/patch_svg.py` (source-preserving edits), `scripts/extract_pdf_text.py` (available Poppler extraction), three references, synthetic expected outputs, and negative test. Versions are pinned by source file hashes recorded at each run; no network service or third-party Python dependency is needed for core operation.
