# Visual comparison and original-source policy

## When to run

Create a derived comparison plot only if the task requests a plot/figure comparison or if the numerical relationships materially affect the answer. Do not add decorative plots to a simple arithmetic check.

## Original inspection protocol

1. Locate the original page, table, or figure using platform PDF text tools.
2. Use platform PDF rendering to save an original page render and a tight crop under `/app/output`. Keep page number and figure/table ID in the ledger.
3. Read axes, units, legends, condition labels, row/column headers, and displayed values. Distinguish printed labels from pixel-estimated heights. Pixel estimates are `reader_inference`, never `author_reported`.
4. Add the original render/crop paths and an honest `original_review` record to the ledger. The engine can copy provided images and emit the derived SVG; it does not replace platform visual inspection.
5. Compare source tuples side by side. Record `consistent`, `conflict`, `partial`, `unreadable`, `missing`, or `not_reported`, including exact conflicting values and conditions. Use `missing` for an unsupplied original figure/render/crop; use `not_reported` only when a supplied source omits information.

If the task asks only for independent recomputation and the numbers do not need visual comparison, omit the plot. If original figures cannot be rendered, state `unreadable` or `missing` as appropriate; do not create a substitute and call it original.

## Derived SVG semantics

The standard-library SVG writer draws labelled signed bars, values, units, legend, and a `DERIVED COMPARISON — NOT ORIGINAL` notice. It supports negative, mixed-sign, and all-zero values with a dynamic zero line and ticks/bars contained in the viewBox. All bars must share one canonical unit; mixed canonical units are rejected rather than silently co-plotted. The default axis label is generated from that unit. An optional `axis_label` must be at most 80 characters and explicitly mention the common unit (for percent, `%`, `percent`, or `percentage`). It is text-based standalone SVG, not a placeholder, and uses extracted ledger tuples only.

A derived plot demonstrates what the extracted numbers look like. It does **not** prove that extraction, OCR, arithmetic, or the source figure is correct. Agreement between two derived products is circular unless checked against the original render/crop.

## OCR and uncertainty

OCR can confuse minus signs, decimal points, percent signs, digits, and table columns. Keep short source quotes, inspect the original crop for decision-critical values, and record uncertainty rather than guessing. No hallucinated error bars, confidence intervals, or original graphic elements are permitted.
