---
name: native-deck-transaction
description: Adapt or generate editable academic PPTX decks through explicit keep/edit/append/remove/reorder transactions on an immutable native OOXML template or starting deck, with source-span evidence, kept-slide identity checks, and real LibreOffice PDF/PNG render QA. Use for template application, content replacement, slide insertion, reordering, and audit-critical PPTX editing without recreating a lookalike theme.
---

# Native Deck Transaction

## Trigger and non-trigger

Use this skill when an actual PPTX starting deck or template must remain the design authority while slide content is adapted, appended, removed, or reordered. It is suitable for scientific decks whose claims must cite exact PDF evidence.

**Do not trigger** for a visual redesign that intentionally replaces the master/theme, for building a deck from screenshots, or when the request explicitly permits a newly designed lookalike deck. Never delete all starting slides to make adaptation convenient, and never mistake theme-token extraction for native template reuse.

## Dependencies and paths

Declared Python dependencies: `python-pptx`, `PyMuPDF`, `Pillow`; ReportLab is used only by the synthetic example. The runner never installs dependencies. Rendering uses `soffice` on `PATH`, then `/Applications/LibreOffice.app/Contents/MacOS/soffice`; preview rasterization uses `pdftoppm` or PyMuPDF. If a capability is absent, report it rather than claiming the corresponding QA.

Run from this bundle directory:

```bash
python3 scripts/run_case.py prepare --input /input --work /app/work --output /app/output
# Read actual task/case, source_index, native_inventory, and the skeleton plan.
# Write validated operations to /app/work/transaction_plan.json.
python3 scripts/run_case.py finish --input /input --work /app/work --output /app/output
```

`--plan /app/work/another-plan.json` is optional on `finish`. Treat `/input` and the original PPTX as immutable. Work files belong under `/app/work`; deliverables belong under `/app/output`. Partial-first: `prepare` immediately writes `result.json` with status `partial`.

## Required workflow

1. Read `/input/task.md`, `/input/case.json`, `/app/work/native_inventory.json`, `/app/work/source_index.json`, and the skeleton `/app/work/transaction_plan.json`. Open actual PDFs when page context is needed. Do not infer a deck role from a domain label or filename: use explicit material roles plus actual slide/master/layout structure recorded by discovery.
2. Confirm the selected `base_path`, `mode`, fixed slide count, audience, and minutes. Resolve ambiguity conservatively and retain it in `uncertainty`. The inventory records every discovered real PDF/PPTX path, PDF line quote IDs and page renders, native layouts/placeholders, and original slide IDs.
3. Produce an explicit transaction plan. Account for **every original slide exactly once** as `keep`, `edit`, or `remove`; use stable IDs for appends and one final explicit `reorder`. Do not rely on implicit deletion.
4. Source-link every edited/new scientific slide with at least one exact page quote. Paraphrases are allowed when the attached quote supports the statement. Support every numeric token in title/bullets from the attached quotes, or set `presentation_metadata: true` only for genuinely nonscientific metadata such as an agenda. Use speaker notes for delivery and source details; the runner appends evidence references automatically.
5. Run `finish`. It applies operations to a copy of the base, uses actual native layouts/placeholders, aspect-fits figures, writes `presentation.pptx`, restores kept slide XML/relationship bytes where feasible, audits the native diff, and renders real PDF/PNG when a renderer exists.
6. **Inspect every rendered page image.** Check meaning, clipping, overlap, image legibility, title/footer collisions, and warning entries in `render_report.json`. Page-edge ink is not an overflow test because native templates may intentionally bleed. If correction is needed, change only authorized plan operations and rerun `finish`, then inspect every page again. After actual visual review, set `meta.visual_review` to `{"status":"complete","pages":[1,2,3],"corrections":[...]}` with the real page list and rerun so the report records the review.
7. Reconcile `result.json`: original `case_id`, all original output-contract fields, honest `status`, sources, uncertainty, change log, and artifacts. Recognizable presentation/PDF/preview/count fields are populated by the runner. Do not call a native or render failure successful.

## Transaction schema

```json
{
  "schema_version": "1.0",
  "mode": "adapt",
  "base_path": "/input/starting.pptx",
  "base_slide_ids": ["original-0001", "original-0002"],
  "meta": {
    "title": "Talk title",
    "audience": "Review committee",
    "minutes": 7,
    "slide_count": 3,
    "minimum_explicit_font_pt": 12,
    "visual_review": {"status": "pending", "pages": [], "corrections": []}
  },
  "operations": [
    {"op": "keep", "id": "original-0001"},
    {
      "op": "edit", "id": "original-0002", "source_slide_id": "original-0002",
      "title": "Response increased by 42%",
      "bullets": [{"text": "The treatment group improved by 42%.", "level": 0}],
      "title_placeholder_idx": 0,
      "body_placeholder_idx": 1,
      "notes": "State the comparison before the number.",
      "figures": [{"source_id": "pdf-0001", "page": 2, "figure": "Figure 1"}],
      "evidence": [{
        "source_id": "pdf-0001", "page": 3,
        "quote_id": "pdf-0001-p0003-l0002",
        "quote": "Results: the response increased by 42% in the treatment group.",
        "section": "Results"
      }]
    },
    {
      "op": "append", "id": "new-takeaway", "layout": "Title and Content",
      "title": "Takeaway", "bullets": ["Use the supported conclusion."],
      "notes": "Close here.",
      "evidence": [{"source_id": "pdf-0001", "page": 4,
        "quote": "The conclusion quoted here must exactly occur on page 4.", "section": "Conclusion"}]
    },
    {"op": "reorder", "final_order": ["original-0001", "original-0002", "new-takeaway"]}
  ]
}
```

Use `layout_idx` from the flattened inventory when layout names are absent or duplicated. Dangling layout indices/names and invalid placeholder `idx` values are rejected. A figure may instead specify an existing `path`; `source_id` + `page` uses the PyMuPDF page render, and `extracted_image_index` can select an extracted raster image. Optional figure `placeholder_idx` must exist on the target layout. Edit operations preserve all unspecified content, speaker notes, shapes, layout, and inheritance; changing an existing slide's layout is rejected. Append requires an actual native layout.

See `references/transaction_semantics.md` for invariants, generation rules, and evidence limits.

## Edit/adapt versus generate

- **Edit/adapt:** start from the selected immutable starting deck. Keep slides remain untouched. Only named edit targets may have specified title/body placeholders, notes, or figures changed. Remove only explicitly listed IDs. Omitted properties are not blanked.
- **Generate:** start from the actual template and its native layouts. Existing slides are recorded example IDs in the inventory (or use explicit `case.example_slide_ids`). Remove only those recorded example slides; non-example originals require keep/edit accounting. Append new content with source evidence. Do not manufacture a theme or add font-global restyling.

Fixed slide count, audience, and time in task/case/workorder are constraints, not suggestions. The final order must contain every surviving original and appended ID exactly once and no removed IDs.

## Outputs and failure handling

Expected outputs:

- `presentation.pptx`: editable native OOXML deck, not a raster facsimile.
- `presentation.pdf` and `previews/preview-NNN.png`: real render products when LibreOffice is available.
- `native_inventory.json`, `transaction_plan.json`, `evidence_map.json`, `native_diff.json`, `render_report.json`, `source_index.json`, `result.json`.

`native_diff.json` checks slide→layout→master→theme membership/hashes, unchanged dimensions/layouts/masters/theme, kept-slide original identity hashes, allowed changed parts, new media, and notes changes. ZIP timestamps or whole-PPTX nondeterminism are not failure criteria. Read `references/ooxml_identity.md` and `references/render_qa.md` before overriding a warning.

If the plan or native audit fails, `result.json` is `failed` when no PPTX exists and `partial` when a usable PPTX exists but validation is incomplete. Renderer/PNG absence likewise yields `partial` with explicit uncertainty. Never silently install packages, substitute a blank deck, remove originals to make a plan pass, claim visual inspection without opening every page, or claim font-fallback detection when neither `fc-list` nor renderer evidence is available.

## Runnable synthetic example

The independently generated **SYNTHETIC / 合成示例** creates a custom-theme multi-layout template, a three-slide starting deck, a four-page paper PDF, runs prepare/fill/finish for a five-slide seven-minute adaptation, verifies real PPTX/PDF/PNG and kept identity, and tests missing-original and dangling-layout rejection:

```bash
python3 scripts/run_synthetic.py --output-root /app/work/native-synthetic
```

All example binaries and reports are written outside the bundle beneath the requested output root. See `examples/synthetic/README.md`.
