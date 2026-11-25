---
name: visual-evidence-atlas
description: Localize and review paper evidence in original rendered PDF pages and crops, linking figure, table, caption, body, panel, row, and column identities without treating captions or generated charts as visual proof.
---

# Visual Evidence Atlas

Use this skill when a paper answer depends on what is visibly present in figures, tables, scans, equations, panels, cells, or their captions and body-text discussion. The deliverable is a reviewable atlas of **original visual evidence**, not a redrawn figure. This is not a numeric formula engine, an argument graph, or a generic line-anchor checker.

## Runtime contract

The runtime provides the actual `/input/case.json`, `/input/task.md`, `/input/papers`, `/app/work`, and `/app/output`. Read the actual task and case before processing. Use `/app/work` for temporary work and `/app/output` for deliverables. Write `/app/output/result.json` with the actual `case_id` and **every field required by that case's `output_contract`**, preserving its nesting, types, required fields, enums, and `additionalProperties: false` at every object level. Do not add convenient top-level keys when the contract forbids them. The synthetic case demonstrates one such nested closed schema; it is not a substitute for reading the real case.

Report status honestly using the contract's exact enum (commonly `success`/`partial`/`failed`; use `complete` only when the contract declares it). Preserve the distinctions `missing`, `unreadable`, `not_reported`, and `conflict`; never collapse them into a single negative. Populate the contract's sources, uncertainty, and change_records fields (or their exact contract equivalents) with traceable entries. If output cannot be completed, still write the closest contract-valid honest result possible, including failures and uncertainty.

Make an early contract-valid draft at `/app/output/result.json` in **fewer than 64 model calls and under 900 seconds**, then enrich only with task-relevant evidence. Directly answer the requested question or translation first. Do not spend the budget building an exhaustive atlas. No network, new packages, personal absolute paths, or filename-based inference about source content are allowed.

## Required evidence workflow

1. **Inventory and extract.** Enumerate actual supplied papers, inspect PDF metadata, page count, permissions, and encryption, and run `pdftotext` with layout preservation where useful. Never infer the paper's content from a filename.
2. **Render originals.** Use `pdftoppm` to render relevant original PDF pages. Make original crops for regions that matter to the answer. Save used original renders and crops under `/app/output`, with stable names and no alteration of their evidence content. Bundle resources must remain text-only, although runtime evidence images may be PNG, JPEG, or other suitable render formats.
3. **Actually look.** Visually inspect the real rendered pages and crops whenever figures, tables, scans, or equations matter. A text extraction, a caption, or an OCR string is not visual inspection. Never claim to have seen an image that was not opened and inspected. The machine validator cannot verify sight: `agent_attested_inspected` is only an agent attestation, must name a change_record, and is never automatic visual-truth verification.
4. **Localize identity.** Record file, `page_id`, zero-based PDF page index, printed page when visible, region kind, bbox, and image dimensions. For figures record panel labels; for tables record table, row, column, and cell identity, including merged or unclear headers. Record crop parentage where relevant. Follow `references/coordinate_conventions.md`.
5. **Link corroboration without erasing direct visual evidence.** Quote the caption exactly and link its source-text character span. Link body anchors and table values similarly. Record caption and body corroboration separately for every decisive visual claim. A caption alone is never proof of an individual cell, row value, panel measurement, or visual trend. However, an agent-attested inspection of the available original table cell, with verified nonempty row and column identity, is direct visual evidence: do not demote it to caption-only merely because body text does not repeat the value. Record absent body corroboration as a limitation. Reserve `unresolved_caption_only_cell` for a cell that was not inspected or whose row/column identity is unclear. Missing, unreadable, not-reported, or conflicting subject regions still block a reviewed resolution.
6. **Preserve uncertainty.** Flag missing pages/regions, unreadable resolution, OCR failure, conflicting text and pixels, hidden or merged headers, double-column reading-order uncertainty, and page-index versus printed-page ambiguity. Keep supplemental material linked to its own normalized file and page identity; never silently merge its numbering with the main paper. Main and supplemental PDFs may each have zero-based page index 0; only repeated indices for the same normalized source are duplicates.
7. **Validate and render.** Create atlas JSON as specified in `references/visual_evidence_rules.md`. Run the deterministic standard-library validator. Treat malformed records as errors and review warnings as unresolved. Render both HTML and Markdown, then read them back and inspect that original images are linked, regions are listed, and unresolved items remain visible.
8. **Answer with provenance.** In `result.json`, connect each decisive statement to region IDs and evidence states. Preserve original images; do not fabricate replacement charts or use a reconstructed chart as proof of the original.

## CLI

Run from this skill directory. All paths below are examples, not runtime assumptions.

```bash
K=/skills/weekly-skill  # 若实际安装路径不同，设为本 SKILL.md 所在目录
python3 "$K/scripts/atlas_tool.py" validate \
  --atlas /app/work/atlas.json \
  --text-source /app/work/paper.txt \
  --image-root /app/output \
  --audit /app/output/audit_report.json

python3 "$K/scripts/atlas_tool.py" render \
  --atlas /app/work/atlas.json \
  --text-source /app/work/paper.txt \
  --image-root /app/output \
  --output-dir /app/output

# 仅合成示例使用 build；真实案例必须按实际 output_contract 另行组装结果。
python3 "$K/scripts/atlas_tool.py" build \
  --atlas "$K/examples/synthetic/atlas.json" \
  --text-source "$K/examples/synthetic/source.txt" \
  --case "$K/examples/synthetic/case.json" \
  --image-root "$K/examples/synthetic/output" \
  --output-dir "$K/examples/synthetic/output"
```

`validate` writes an audit and exits nonzero for malformed input. `render` refuses errors but permits reviewed warnings and writes self-contained, dependency-free HTML and Markdown with local original-image links. `build` additionally creates a result for the supplied demonstration contract. For a different real output contract, assemble that exact result separately and use the validator/renderer for atlas evidence.

Run the offline standard-library release regressions with `bash tests/run_tests.sh`. The suite covers impossible bboxes, missing corroboration, every blocking subject-region state, independent main/supplemental zero-based pages, normalized-source duplicate detection, and the inspected-cell/caption-only distinction.

## Special evidence policies

- **Vector figures:** inspect a raster render of the original page even if text or paths can be extracted. Extraction helps localization but does not establish visible geometry, color, or panel identity.
- **Multi-panel figures:** use stable panel IDs and literal panel labels; note absent, duplicated, or ambiguous labels. Do not map panels by reading order when labels conflict.
- **Supplemental material:** give each PDF its own source identity and page sequence. Link cross-references explicitly and retain printed-page differences.
- **Permissions or encryption:** record permission/encryption failures as `unreadable` or `missing` as appropriate. Do not bypass access controls or claim visual inspection from text alone.
- **OCR failure:** retain the failed state and original render. OCR can supply uncertain anchors but cannot turn an unreadable region into inspected evidence.
- **Reading order:** double columns and nonstandard layouts require an explicit reading-order state. Keep `uncertain` visible until actual page inspection resolves it.
- **No evidence substitution:** generated diagrams may illustrate an interpretation only if clearly labelled as interpretation and kept out of evidence. Never replace an original crop with one.

## Synthetic example

The example is entirely fictional and visibly marked **SYNTHETIC**. Its original SVG page fixture is a text stand-in for a rendered original page because this bundle contains no binaries. Run:

```bash
bash examples/synthetic/run_example.sh
# Or provide a different output root:
bash examples/synthetic/run_example.sh /app/work/synthetic-atlas-output
```

The script copies the original SVG page and crop fixtures into the output root, performs real validation, renders HTML and Markdown, writes a closed-contract `result.json`, and writes `audit_report.json`. The included table-cell claim is `reviewed_corroborated` because the agent attests direct inspection of the original cell with verified row/column identity; its absent body corroboration remains a visible limitation rather than erasing that direct evidence. Double-column reading order remains uncertain, so the result is honestly `partial`.
