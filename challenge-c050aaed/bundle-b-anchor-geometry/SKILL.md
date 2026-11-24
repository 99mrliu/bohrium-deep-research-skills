---
name: anchor-geometry
description: >-
  Anchor geometry & coordinate fidelity for reading-annotation extraction
  (批注提取): resolve raw PDF annotation marks (Highlight/Underline/Squiggly/
  StrikeOut/FreeText/Ink) to exact page text via quad/word-box intersection
  (锚点 resolution, 坐标 engineering), repair 双栏 (two-column) reading order,
  correct 扫描件 (scanned-page) / OCR漂移 (OCR coordinate drift) by fuzzy
  re-anchoring, and independently 回验 (re-verify) every anchor so each
  annotation traces back to its exact page and position. Use whenever
  annotation extraction must be geometrically correct and auditable.
---

# Anchor Geometry & Coordinate Fidelity

The correctness layer of annotation extraction. Given raw annotation marks
(quads/rects, type, color) plus page words WITH coordinates, it resolves
exactly which text each mark covers, fixes two-column reading order, corrects
OCR/scanned-page drift, and re-verifies every anchor independently.

## When to use

- Extracting the exact text a Highlight/Underline/Squiggly/StrikeOut covers.
- Two-column (or multi-column) PDFs where serial text extraction garbles order.
- Scanned pages / OCR word boxes whose coordinates drifted from the marks.
- Any time an annotation must be traceable to its page + bbox and re-checkable.
- NOT for writing notes, judging content, or retrieval (see Boundaries).

## Inputs & runtime contract

- Case inputs live at `/input/case.json` and `/input/task.md`; real materials
  (marked-up PDFs, scans, web clips) are under `/input`.
- Work under `/app/work`; deliverables go to `/app/output`.
- `/app/output/result.json` MUST contain the original `case_id` (copied
  verbatim) and EVERY field named by the case's `output_contract` — read that
  contract dynamically from case.json at runtime; never hardcode field names.
- Write a PARTIAL result.json EARLY (before heavy work) and improve it in
  place. `status` ∈ {complete, partial, failed}. Include `sources`,
  `uncertainty`, and `change_records`; record every skip, failure, conflict
  and recovery. Never fabricate text an anchor did not resolve to.
- Budget-aware: all scripts here are deterministic single passes over text
  artifacts — cheap; spend model requests on judgement, not on re-runs.

## Producing the words+annotations artifacts in the eval environment

The scripts consume two text artifacts per document (see
`references/anchor_schema.json`):

1. `annotations.jsonl` — one JSON object per raw mark: `{annotation_id, file,
   page, type, category, color_rgb, quadpoints or rect, contents, author}`.
2. `pages/<file>/page-NNN.words.tsv` — `word \t x0 \t y0 \t x1 \t y1
   [\t origin \t confidence]`, origin top-left, y down, page number 1-based
   zero-padded (`page-001.words.tsv`).

Probe the environment in Python (`shutil.which`) and use the first available:

- `pdftotext` (poppler): `pdftotext -bbox-layout in.pdf out.html`, then parse
  `<word xMin=".." yMin=".." xMax=".." yMax="..">` per `<page>` with stdlib
  `xml.etree`/regex. Coordinates are already top-left origin.
- PyMuPDF (`import fitz`): words via `page.get_text("words")`
  (x0,y0,x1,y1,word,block,line,word_no); annotations via `page.annots()` —
  `a.type`, `a.vertices` (quadpoints), `a.rect`, `a.colors["stroke"]`,
  `a.info` (`content`→contents, `title`→author). All top-left origin.
- Scanned page (no text layer: `page.get_text()` empty): run the ocr-tool path
  provided by the task; write words with `origin=ocr` and per-word confidence.
- If NEITHER a text extractor nor an OCR tool exists: record an honest
  per-file failure in result.json (`status` partial/failed, `change_records`
  entry) and continue with the other files. Never invent word boxes.
- If you must parse raw PDF objects yourself (pypdf), convert from PDF's
  bottom-left origin: `y_tl = page_height - y_pdf`
  (see `references/geometry_notes.md` §1).

## Workflow

Run from the case work dir (paths below assume the skill is installed at
`/skills/weekly-skill`):

```bash
S=/skills/weekly-skill/scripts
# 1. build artifacts (above) -> /app/work/annotations.jsonl, /app/work/pages/
# 2. resolve every mark geometrically
python3 $S/anchor_resolve.py --annotations /app/work/annotations.jsonl \
  --pages-dir /app/work/pages --out /app/work/resolved.jsonl          # exit 0|2
# 3. independent second-pass verification
python3 $S/anchor_verify.py --resolved /app/work/resolved.jsonl \
  --pages-dir /app/work/pages --out /app/output/verify_report.json    # exit 3 if any 'failed'
# 4. repair OCR/drifted anchors (no-op for clean born-digital pages)
python3 $S/drift_correct.py --resolved /app/work/resolved.jsonl \
  --pages-dir /app/work/pages --out /app/work/corrected.jsonl         # exit 3 if any 'unrecoverable'
# 5. re-verify the corrected anchors
python3 $S/anchor_verify.py --resolved /app/work/corrected.jsonl \
  --pages-dir /app/work/pages --out /app/output/verify_report_corrected.json
# 6. assemble /app/output/result.json: case_id + dynamic output_contract
#    fields, per-anchor records from corrected.jsonl, verify summaries,
#    sources, uncertainty, change_records.
```

## Outputs

- `resolved.jsonl` — per annotation: `anchored_text`, `word_indices`,
  `coverage` (fraction of quad area covered by matched words), `page`, `bbox`,
  `column_count`, `anchor_kind` (quad | rect | nearest_block, with
  `anchor_distance` for FreeText-style marks), `page_origin`, plus ALL original
  metadata preserved verbatim (type/category/color_rgb are never bucketed).
- `verify_report.json` — per-anchor table (ratio, class exact/normalized/
  drifted/failed/skipped) + overall rates. Exit 3 ⇔ ≥1 failed anchor.
- `corrected.jsonl` — resolved records + `correction` object: `ok` |
  `corrected` (old/new bbox, ratio) | `unrecoverable` (best_ratio, never
  guessed) | `skipped` | `not_checked`. Exit 3 ⇔ ≥1 unrecoverable.

## Failure handling

- Missing page words → `status=no_words_file` (in-band, not a crash).
- Quads match nothing → `status=empty_match` with the quad recorded.
- Low coverage (<0.5) → `drift_suspected=true`, fed to drift_correct.
- Fuzzy re-anchor below 0.75 → `unrecoverable`; the record stays untouched.
- All fatal I/O errors → exit 2 with `FATAL:` on stderr. Quality gates
  (verify failures, unrecoverable drift) → exit 3. Success → exit 0.
- Every degradation lands in result.json `change_records` with a reason.

## Boundaries

This skill does NOT write reading notes or summaries, does NOT retrieve or
search external knowledge, and does NOT judge whether the marked content is
correct or important. It only guarantees that whatever downstream note-writing
consumes is anchored to the right page, position, and exact text.

## Minimal example

A fully synthetic, text-only end-to-end run (single column, two-column repair,
FreeText margin note, OCR drift correction, one honest unrecoverable) with
real observed outputs and negative tests: see `examples/README.md` and
`examples/EXPECTED.md`. Core check — a sentence flowing across a two-column
break resolves to `kilo … tango uniform … date` (column order), NOT the
garbled `uniform … date kilo … tango` of naive serial reading.
