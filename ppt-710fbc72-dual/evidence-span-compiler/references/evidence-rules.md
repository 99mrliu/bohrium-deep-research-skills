# Evidence anchoring and compile-gate rules

## Two-level identity

A **span ID** identifies an extracted source location. A PDF span ID resembles `S001.p0002.b004.l00s00`: source, one-based page, block, line, and span order. It is deterministic for an unchanged source/extractor version. Each record includes the raw text span, normalized text, complete text block, bounding boxes, source ID, and source SHA-256. Text work orders use corresponding deterministic one-page records.

An **evidence ID** (`E01`, etc.) is a plan-local anchor containing `span_id` and a raw `quote`. This separation lets the agent quote a precise clause while retaining the ledger's complete block context. `evidence_map.json` resolves every slide anchor to source/page/span, raw quote, qualifier, and context.

The compile gate rejects unknown spans, duplicate IDs, empty quotes, unknown references, and missing slide/bullet/figure evidence closure. It recomputes hashes for referenced sources and assets. If a file changed, rerun `prepare`; do not assume old IDs or quotes still identify the same text.

## Quote matching

The raw quote and raw span are never overwritten. For matching only, both receive Unicode NFKC normalization, common ligature expansion, soft-hyphen removal, and whitespace collapse. The normalized quote must be an exact contiguous substring of the normalized referenced span. A quote assembled from different spans is not one anchor: create separate anchors or choose a ledger span that contains the complete snippet.

This is intentionally stricter than semantic similarity. Paraphrase belongs in slide text, with exact evidence quotes in the plan. Preserve qualifiers in narrative and notes; the `qualifier` field is an annotation, not permission to alter a quote.

## Numeric provenance is not substring matching

The validator extracts numbers as tokens with optional signs, decimal/scientific notation, thousands separators, percentages, and common scientific units. It compares normalized numeric value and unit against tokens in the evidence bound to that specific title, takeaway, or bullet. Consequently:

- `18%` is not supported by a bare `18`;
- `0.5` can match an equivalent numeric spelling only when units agree;
- the digits in `18` do not accidentally support `8` or another substring;
- sentence-ending punctuation such as `Figure 1.` remains a valid number token;
- each unsupported token reports slide ID, unit, token, and bound evidence IDs.

No numeric token is automatically discarded. Figure/Table reference tokens can additionally use the selected asset's original source caption, which is itself source-anchored. Dates, section identifiers, and metadata still require source/task anchoring. Slide numbers inserted by presentation software do not require invented evidence. Speaker guidance in `notes` is not rendered slide copy; factual visible text must be in validated fields.

Numeric agreement establishes provenance, not scientific correctness. Agents must still check denominators, comparison direction, rounding, conversions, experimental groups, and context. A number copied from an unrelated sentence can pass token equality only if the agent bound the wrong evidence, so the exact quote and complete block must also support the proposition.

## Source hierarchy and conflicts

1. Follow the explicit work order for audience, duration, slide count, required materials, and output contract.
2. Use supplied source PDFs for scientific claims. Do not let template example text become evidence.
3. Use task/work-order text spans to anchor presentation metadata such as requested count or duration.
4. Treat source captions as descriptions of cited assets, never as newly generated experimental results.
5. Preserve limitations and uncertainty. If sources conflict, present the conflict with separate anchors or disclose it; do not average, reconcile, or choose silently.

Templates supply visual/layout structure only. The synthetic fixture is never scientific evidence for a real case.

## OCR and extraction limitations

PyMuPDF extracts the existing PDF text layer; this bundle does not perform OCR. Scanned pages, outlined glyphs, equations, and multi-column reading order may be incomplete or misleading. Tables and figures can be vector drawings rather than embedded images. A page preview therefore accompanies every extracted PDF page, and caption crops require visual confirmation.

If a needed source is scanned or extraction is garbled, disclose the affected source/pages and keep status partial/failed unless an agent-available OCR method supplies verifiable text. Do not transcribe unseen science or silently infer missing labels. Ligature/whitespace normalization does not repair bad reading order or OCR errors.

Caption candidates are proposals, not ground truth. Neighboring image/drawing/text bounds can over-select nearby material or under-select a label. Explicit PDF-point bboxes and the render-inspect-correct loop are part of the evidence model.
