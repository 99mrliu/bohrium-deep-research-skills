# Actual PDF, biological source, Figure 03, and semantic review

## The two independent questions

1. **Provenance:** does this exact normalized span occur at this unique location in these exact source bytes?
2. **Meaning:** after reading actual context and inspecting original graphics, does the proposed visual encode the same entity, quantity, direction, relation, ordering, scope, and exclusions?

A `yes` to (1) never answers (2). A sentence can mention a control and still be used to justify the wrong treatment; a quote containing “A connects to B” does not necessarily identify a material flow or its direction. Conversely, an original figure may clarify geometry that prose does not, but only after direct visual inspection. Record both checks separately.

## PDF/methods workflow

- Inventory the actual `/input` payload and `/input/case.json`; do not infer content from a filename or domain label.
- Use the supplied environment PDF tools when available. For text-layer PDFs, `scripts/extract_pdf_text.py` calls preinstalled `pdftotext -layout -enc UTF-8`, preserves form feeds, hashes the PDF and extracted text, and fails if no tool/text is available.
- Retain `/app/work` intermediates and deliver relevant source-location summaries under `/app/output`. The extraction is a locator surrogate; read the real PDF page view for scientific context, superscripts, figure labels, line wrapping, and table structure.
- Read surrounding paragraphs, captions, abbreviations, and referenced figures. Do not dehyphenate or correct a quote automatically. Select a longer verbatim excerpt and use the documented whitespace normalization.
- If PDF pages have printed labels different from extraction positions, include both and verify the mapping visually. Do not silently substitute page numbers.
- Scanned pages without text require an actually available environment OCR tool and an explicit OCR uncertainty. The core does not perform OCR and does not turn an OCR guess into an exact match. Missing readable material is `partial` or `failed`, not an invitation to reconstruct.

## Primary biological source / Figure 03 inspection

The fixed task specifically calls for primary biological sources for Figure 03. Identify the actual primary source from the case, not from a label such as “biology” or from a filename alone. Follow references supplied by the case only to actual available material. If the original is not supplied or accessible, report that limit; do not create an authoritative replacement.

Inspect the original figure at native or enlarged resolution (or the actual PDF page rendering) using the runtime's visual capability. For each relevant panel record:

- file/hash/version and source identity;
- printed figure/panel labels and actual page position;
- visible entity names, marker styles, scale bars, units, and labels;
- arrow tails, arrowheads, branching, joining, crossings, feedback/recycle, and line-style meaning;
- whether a relation is material, energy, information, temporal, or only spatial;
- what is absent in the original versus explicitly forbidden by prose;
- comparison to each proposed visual and any conflict.

Do not infer direction from left/right placement alone when no arrow or textual ordering is present. Do not interpret a crossing as a junction without a visual/source basis. Do not “complete” a biological mechanism using background knowledge. Do not turn an absent detail into an observed negative unless the visual scope supports that claim.

When a figure is only available inside a PDF, `visual_path` may be the exact PDF bytes; `inspected_panels` and locator identify its page/panel. When an original PNG is available, use its exact `visual_path` hash and inspect the PNG itself. The text `path` still contains actual caption/transcript evidence for normalized spans. If transcription is authored by the agent rather than extracted verbatim, label it and use source prose for quotes; never claim transcript text proves figure meaning.

## Conflict protocol

1. Preserve both exact spans/locators and figure observations.
2. Name the conflict precisely: identity, direction, order, count, unit, scope, version, or CSV mapping.
3. Check whether context/panel/version resolves it without preference guessing.
4. A resolved conflict records rationale and visual treatment. An unresolved conflict blocks the gate.
5. Deliver supportable portions as `partial`, listing omitted contested elements. Never silently harmonize.

## Review rounds and evidence

Use at most **two bounded review rounds**:

- Round 1: provenance + actual PDF/figure semantic audit + CSV values + source/visual coverage; batch all corrections.
- Round 2: only targeted failed spans, known semantic mismatches, edit preservation, and export/canvas/font checks.

Do not spend rounds on decorative refinement or repeatedly asking an exporter to compensate for unsupported science. Preserve the first failed report and final report in `/app/work` when useful, and summarize material corrections in `change_records`.
