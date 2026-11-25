# SYNTHETIC / 合成示例

This example is entirely **SYNTHETIC / 合成** and is not scientific evidence. It generates a six-page research-style PDF with real text spans, one vector chart, `Figure 1` and `Table 1` captions, plus a genuine PPTX template containing pre-existing slides, multiple native layouts, and custom theme colors. The work order explicitly requests **6 slides / 8 minutes / methods reviewers**.

## Exact command

From this bundle's root directory, with Python dependencies and LibreOffice already available:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 examples/run_synthetic.py --output-root /app/example-runs/evidence
```

Choose a different writable output root if `/app/example-runs` does not exist, but keep generated files **outside the bundle**. The runner sets `PYTHONDONTWRITEBYTECODE=1` for its subprocesses. It does not access the network or install dependencies.

## What it does

1. Generates `input/research.pdf`, `input/template.pptx`, `input/case.json`, and `input/task.md` under the specified output root.
2. Runs `prepare`, reads actual extracted span/asset IDs, and authors a six-slide evidence-linked `work/deck_plan.json` programmatically.
3. Runs `finish`, which validates the plan, builds the editable deck from the actual template, exports with discoverable LibreOffice, and renders six PNGs.
4. Verifies the original `case_id`, every nested output-contract field, six PPTX slides and evidence notes, removal of old template slides, six real PDF pages and expected text, original Figure/Table captions, and nonblank PNG dimensions. It also asserts that the table crop includes the rightmost Response column.
5. Runs an additional adapt regression: prepares the same real two-slide base in `adapt` mode, edits both originals in their native layouts, appends four evidence-linked slides without implicit deletion, and verifies a second real six-page PPTX/PDF under `adapt-output`.
6. Performs a meaningful negative test by replacing an evidence quote with text absent from the task. `finish` must exit nonzero, emit `quote_mismatch`, and write `status: failed` to `negative-output/result.json`. The good plan is restored afterward.

The full positive test requires a discoverable renderer because it asserts `status: success`. On a renderer-less system the core CLI still produces a PPTX and an explicit partial result, but this end-to-end success assertion will correctly refuse to claim a verified render.

## Expected generated files

Under the chosen output root:

- `verification.json`: positive/negative status and actual PNG dimensions;
- `work/source_ledger.json`, `work/asset_candidates.json`, `work/page_previews/*.png`;
- `work/input_inventory.json`, `work/template_inventory.json`, `work/deck_plan.json`;
- `output/presentation.pptx`, `output/presentation.pdf`;
- `output/previews/slide-01.png` through `slide-06.png`;
- `output/evidence_report.json`, `output/evidence_map.json`, `output/render_report.json`, `output/build_report.json`;
- `adapt-output/presentation.pptx`, `adapt-output/presentation.pdf`, and six adapt previews;
- `output/result.json` with `status: success` and populated contract fields;
- `negative-output/evidence_report.json` and `negative-output/result.json` documenting the rejected quote.

Inspect all six output PNGs visually even though the runner checks their dimensions and page text. Use `output/render_report.json` for renderer diagnostics and page text, and `output/evidence_map.json` to audit each slide's raw quotes, context, qualifiers, sources, pages, and asset bindings.
