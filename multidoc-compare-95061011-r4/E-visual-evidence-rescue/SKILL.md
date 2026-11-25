---
name: visual-evidence-rescue
description: Recover comparison evidence trapped in PDF tables, multirow cells, captions, and figure panels by combining normal/layout text, physical-page regions, rendered-page visual inspection, and uncertainty-preserving extraction records.
---

# Visual Evidence Rescue

## Center and limits

Use this Skill when prose-only extraction would lose crucial values in PDF tables or figures. The primary artifact is a **source-region evidence map**, not a prose summary. This is not corpus fingerprinting, a numeric unit-conversion library, or generic replay automation. Python tools recover geometry and validate provenance; the agent performs all scientific interpretation.

Never pool unlike datasets, dyes/pollutants, materials, tasks, metrics, units, or experimental budgets. Do not silently convert units. Preserve `not_reported` and `noncomparable`; neither means zero. Never manufacture a number from an unreadable region.

## Required evidence model

For every source region record:

- exact `source_document_id` from the workorder;
- one-indexed **physical PDF page**, including front matter in the count;
- `region_type`: `prose`, `table_row`, `figure_panel`, or `caption`;
- stable supplied `paragraph_id` for prose, with no invented replacement;
- stable supplied `region_id` for nonprose where available, otherwise a deterministic unique ID;
- `paragraph_id` on nonprose regions linking the relevant caption or prose context;
- exact region text and enough geometry/metadata to inspect the source again.

A table row also needs its full header path, units, sample split, aligned cell values, and carried multirow context. A figure panel needs its panel labels. Captions provide context but **cannot prove numeric curve values**. Store figure read-offs as `read_off_figure` with `estimate` and/or `range`, explicit uncertainty, visual-inspection method/notes, and inspected image/text paths; never store them as exact `value` numbers.

## Workflow

1. **Read the runtime contract.** Use `/input/case.json`, `/input/task.md`, `/input/comparison-workorder.json`, and actual PDFs/text. Keep the original case ID and every `output_contract` field. Preserve supplied source, paragraph, and region IDs exactly. Work only under `/app/work`; final artifacts belong in `/app/output`.
2. **Create dual text streams.** Run `scripts/visual_evidence.py ingest`. It writes normal and `-layout` UTF-8 text by calling `pdftotext` for PDFs, without disabling form feeds. Text inputs are copied into both streams. Check `ingest-manifest.json` and clear any missing-Poppler error rather than pretending success.
3. **Inspect structure before values.** Compare normal and layout streams page by page. Read table headers, units, sample splits, panel labels, and captions before transferring values. Use `parse-layout` only to draft simple aligned rows. Verify or correct its drafts manually, especially carried blank cells: “continued” or repeated multirow labels must retain their parent context.
4. **Render and see relevant pages.** For any table whose alignment is ambiguous and every figure carrying needed data, run `render-pages` (Poppler `pdftoppm`) and inspect the resulting PNG using agent vision and/or OCR. Record actual output paths. OCR is a reading aid, not authority. If the panel remains unreadable, use `not_reported` or `noncomparable` with a reason rather than guessing.
5. **Populate an enriched workorder.** Copy the input workorder to `/app/work/comparison-workorder.enriched.json` and add region-backed documents, regions, and extraction records. Keep the supplied ingestion paths. See `references/protocol.md` and `references/workorder-format.md`. Assign `matrix_fields` explicitly and give every document an extraction for every requested field, including `not_reported`/`noncomparable` records.
6. **Test compatibility before synthesis.** Every quantitative record must explicitly establish `task`, `metric`, `units`, `material`, `pollutant`, and `budget`. For derived values, identify all `derived_from` records and the derivation expression. All qualifiers plus `dataset_id` and `dye_id` must agree; multi-input derivations with unknown dataset/dye fail. The renderer never averages or pools.
7. **Validate, render, reread.** Run `validate`, then `render` with the enriched workorder and ingestion manifest. Inspect `comparison-matrix.md`, `source-regions.md`, and `result.json`. Confirm every document appears with exact source/paragraph IDs, every nonprose value resolves to its region, the case ID is exact, all contract keys are populated as applicable, and figure uncertainty and actual visual paths remain visible.
8. **Report honestly.** Result status must describe partial/unreadable/missing evidence. Sources and change records should include dual text streams, table drafts, and visual inspection paths as applicable. Keep uncertainties attached to their records. Unknown custom contract fields remain null with a warning unless supplied through `result_fields`; do not fabricate content to fill them.

## Commands

From this Skill directory (defaults target the runtime contract):

```bash
python3 scripts/visual_evidence.py ingest \
  --workorder /input/comparison-workorder.json \
  --input-root /input --work /app/work

python3 scripts/visual_evidence.py parse-layout \
  --input /app/work/layout/DOCUMENT.txt \
  --source-document-id EXACT_ID --paragraph-id EXACT_PARAGRAPH \
  --output /app/work/table-drafts/EXACT_ID.json

python3 scripts/visual_evidence.py render-pages \
  --pdf /input/documents/source.pdf --pages 2,4-5 \
  --output-dir /app/work/page-images

python3 scripts/visual_evidence.py validate \
  --case /input/case.json \
  --workorder /app/work/comparison-workorder.enriched.json \
  --manifest /app/work/ingest-manifest.json

python3 scripts/visual_evidence.py render \
  --case /input/case.json \
  --workorder /app/work/comparison-workorder.enriched.json \
  --manifest /app/work/ingest-manifest.json --output /app/output
```

Only Python's standard library is used by the tools. PDF ingestion and rendering require existing Poppler `pdftotext`/`pdftoppm`; the tools issue explicit errors when unavailable. PNG/PDF previews are runtime artifacts, never required bundle resources.

## Synthetic example and negative checks

The example has three fictional UTF-8 layout-text documents, actual form-feed page separators, aligned tables, a carried multirow material cell, unreported cells, noncomparable degradation, and a figure-only estimate. It contains no binaries.

```bash
bash example/run_example.sh
python3 scripts/test_failures.py
```

Read outputs under `example/output/`. Tests prove rejection of a caption-only numeric claim, missing region, unlike-dye pooling, and missing quantitative budget; they also check table carry-forward, list/dict output contracts, exact case ID, and complete result fields.
