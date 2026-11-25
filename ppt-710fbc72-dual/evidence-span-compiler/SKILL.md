---
name: evidence-span-compiler
description: Compile source-grounded academic presentations by adapting real PPTX templates, binding every factual slide unit to stable PDF page/block/span evidence, checking quote and numeric provenance, and rendering verified PPTX/PDF/PNG artifacts.
---

# Evidence Span Compiler

Use this Skill when a presentation must be adapted from supplied research sources and a real PPTX template, especially when claims, numbers, figures, qualifiers, or citations must remain auditable. Do **not** trigger for a free-form presentation without sources, a purely visual redesign with no factual adaptation, or a request that does not involve a presentation.

## Non-negotiables

- Read the actual `/input/case.json`, `/input/task.md` (when present), every discovered source PDF, the work order, and the actual PPTX template. Recursive discovery and content classification are implemented by `prepare`; do not choose sources merely by filename.
- Make source text—not a generic presentation plan—the narrative authority. Read enough surrounding block/page context to preserve population, polarity, units, uncertainty, limitations, and qualifiers.
- Never invent science, citations, data, audience, duration, or slide count. Missing task parameters stay null and are disclosed.
- Never relabel a cited Figure/Table as the deck authors' own result. Display the extracted source caption verbatim.
- Preserve factual content when validation fails. Revise or bind it; do not silently delete it to make a gate pass.
- Do not access a network, assume personal paths, install packages silently, push GitHub, create traces, or submit anything.

Dependencies are only Python 3, `python-pptx`, `PyMuPDF`, and `Pillow`; `reportlab` is used only by the synthetic fixture. Inspect availability and report missing dependencies. The renderer is discoverable LibreOffice/`soffice`; no renderer is bundled.

## Input/output contract

Standard runtime paths are `/input`, `/app/work`, and `/app/output`. `case.json` may represent `output_contract` as a dict or list, and its `fields` member may itself be a list or dict. Preserve the original `case_id` and every contracted output field. Recognizable names such as `editable_source`, `export_artifact`, `content_map`, `compliance_checks`, and `exceptions` receive semantic values. Unknown generic fields remain honestly null. Every result also has:

- `status`: `success`, `partial`, or `failed`;
- `sources`, `uncertainty`, `change_log`, and `artifacts`;
- concrete PPTX/PDF paths only when those artifacts actually exist.

Use partial-first operation. `prepare` writes a partial `result.json`. Validation/build failures write `failed`. A valid PPTX without a renderer or with incomplete rendering is `partial`, never success.

## 1. Prepare upstream truth

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_case.py prepare \
  --input /input --work /app/work --output /app/output
```

Read these generated files before authoring:

- `source_ledger.json`: real PyMuPDF text spans, deterministic `S….p….b….l…s…` IDs, raw text, full block context, page/bbox, source path and SHA-256;
- `page_previews/*.png`: every source page;
- `asset_candidates.json`: Figure/Fig/Table captions and conservative crop proposals;
- `input_inventory.json`, `template_inventory.json`: content-classified files and valid masters/layouts/placeholders/theme details;
- `deck_plan.skeleton.json`: parsed task parameters and selected template only. It intentionally contains no invented narrative.

If multiple valid templates exist, inspect them and set `template_path` explicitly. If no valid template exists, disclose the blocker and produce a failed/partial result rather than substituting an unstated template.

Inspect source page previews when extraction order, qualifying context, or a crop is uncertain. Text-layer extraction is not OCR; scanned pages require disclosure and an available external OCR process, not fabricated transcription. See `references/evidence-rules.md`.

## 2. Author the evidence-linked plan

Copy the skeleton to `/app/work/deck_plan.json`, then write a concise narrative appropriate to the explicitly requested slide count, time, and audience. Allocate claims before styling: context/question, source-grounded evidence, interpretation with qualifiers, and conclusion only where supported. Do not fill slides with generic background merely to reach a count.

Plan structure:

```json
{
  "schema_version": "1.0",
  "case_id": "original-case-id",
  "mode": "generate",
  "task_parameters": {"slide_count": 6, "time_minutes": 8, "audience": "methods reviewers", "missing": []},
  "template_path": "/actual/input/template.pptx",
  "remove_slide_ids": [],
  "evidence": [
    {
      "id": "E01",
      "span_id": "S001.p0002.b004.l00s00",
      "quote": "Raw source snippet copied exactly from this span.",
      "qualifier": "Optional short preservation note; does not replace source context."
    }
  ],
  "slides": [
    {
      "id": "s1",
      "kind": "title",
      "title": "Source-grounded title",
      "takeaway": "Supported framing statement.",
      "bullets": [{"text": "A factual bullet with 18% anchored to E02.", "evidence": ["E02"]}],
      "notes": "Speaker guidance that preserves limitations.",
      "evidence": ["E01", "E02"],
      "figures": [
        {"asset_id": "S001.p0003.b008.asset", "evidence": ["E03"],
         "bbox": [85, 186, 515, 447]}
      ],
      "layout_name": "Optional exact native layout name"
    }
  ]
}
```

Every slide requires `id`, `kind`, `title`, `takeaway`, `bullets`, `notes`, `evidence`, and `figures`. Allowed kinds are `title`, `content`, `section`, `figure`, `table`, `summary`, and `closing`. Use `layout_name` **or** `layout_index` only when selection is intentional; normally let the builder choose by kind and placeholder capability.

For `mode: generate`, the base is the actual template and its recorded example slides are removed. For `mode: adapt`, the base is the actual starting deck: account for every `original-NNNN` ID exactly once, either as a slide's `source_slide_id` or in top-level `remove_slide_ids`. Existing slide layouts remain unchanged. Set `preserve: true` on an original-targeted slide to retain its visual content while appending evidence to its existing notes; otherwise the title/body/figures are explicit edits. New slides omit `source_slide_id`. Do not use adapt fields in generation mode. The inventory contains the original IDs and source text needed to author this mapping.

Evidence rules:

1. Evidence IDs are plan-local quote anchors; span IDs are stable source locations. Copy `span_id` and raw `quote` from the ledger. Matching tolerates whitespace, Unicode ligatures, and NFKC differences, but the raw quote is retained.
2. Bind title/takeaway framing through slide `evidence`. Bind each bullet explicitly with `{text, evidence:[…]}`. A string bullet inherits slide evidence and produces a warning. All bullet/figure IDs must also occur in the slide-level closure.
3. Numeric/scientific claims require their own supporting anchors. Every numeric token is checked against bound quote tokens with numeric value **and unit**; arbitrary substrings do not pass. Source-anchored dates, section numbers, metadata, and Figure/Table references are supported. Generated slide numbers need no fake source quote.
4. Select assets only by `asset_id`. `bbox` is optional `[x0,y0,x1,y1]` in PDF points with a top-left origin. Inspect the candidate's page preview and crop result; explicitly correct the bbox if the proposal misses labels, columns, legends, or context. Do not stretch a crop to fill space.
5. Budgets prevent overflow: title ≤90 characters, takeaway ≤220, bullet ≤170, ≤6 bullets, ≤900 total characters per slide, and ≤2 assets. No explicit text is below 14 pt. Tighten the narrative rather than shrinking fonts.

## 3. Compile, render, and inspect

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_case.py finish \
  --input /input --work /app/work --output /app/output
```

`--input` may be omitted when using the prepared `case_snapshot.json`. Validation errors exit nonzero and preserve the plan plus an honest failed result. Read `evidence_report.json` for actionable slide/unit/token/span locations; fix the underlying binding and rerun.

The builder opens the actual template/starting deck, applies only the generation/adapt operations above, preserves masters/layouts/theme, uses native title/body placeholders by type and index, includes speaker notes with every evidence ID and source reference, crops source assets, and aspect-fits images within native body geometry rather than fixed widescreen coordinates. Title typography remains inherited. LibreOffice discovery checks `SOFFICE`, `PATH`, and standard system locations including `/Applications/LibreOffice.app/Contents/MacOS/soffice`. PDF pages become real PNGs through PyMuPDF; expected visible text is compared page by page to flag possible clipping or substitution.

**Visually inspect every `/app/output/previews/slide-*.png`, not just a contact sheet or file count.** Check text clipping/overflow, placeholder collisions, minimum legibility, scientific wording, original captions, crop labels/axes/legends/columns, and aspect ratio. Compare factual wording with `evidence_map.json` and `render_report.json` page text. For each defect, edit `deck_plan.json` or an explicit asset bbox and rerun `finish`; repeat until every page passes. If a defect cannot be corrected, leave `uncertainty`/`exceptions` explicit and use partial/failed status as appropriate.

Successful outputs normally include:

- `presentation.pptx` (editable), `presentation.pdf`, and `previews/slide-*.png`;
- `evidence_report.json`, `render_report.json`, `evidence_map.json`, and `build_report.json`;
- `result.json` populated from the original contract.

When no renderer is available, retain and report the PPTX, the export diagnostic, missing previews, and partial status. Do not create fake previews or claim visual verification.

## References and validation example

Read `references/evidence-rules.md` for anchoring, numeric/source-hierarchy rules, and OCR limitations; `references/template-and-rendering.md` for template/crop/render behavior. `examples/README.md` contains the exact **SYNTHETIC / 合成示例** command. Its runner creates the source/template outside the bundle, compiles six slides, verifies all output classes and contract fields, and proves that an unsupported quote is rejected.
