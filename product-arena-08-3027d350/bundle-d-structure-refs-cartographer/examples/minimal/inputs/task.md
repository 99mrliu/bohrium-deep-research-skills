# Task (synthetic smoke test)

The case PDF-derived page text is `inputs/pages.txt` (4 pages, `=== page N ===`
markers). Produce, into the output directory:

1. A multi-level heading tree and a reconstructed TOC with page anchors.
2. A structured reference list: 6 entries (3 numbered-bracket, 2 author-year,
   1 deliberately corrupted). The corrupted entry must keep
   `parse_status: "raw"` with all fields null except `raw`.
3. A figure/table caption index with a two-way caption/mention cross-check.
4. A `result.json` honoring every field of `output_contract` in `case.json`.

Known planted anomalies (must be flagged, not fixed):
- Section `2.2` is absent while `2.2.1` exists (missing parent / level jump).
- `Table 1` has a caption but no in-text mention.
- `Fig. 2` is mentioned in text but has no caption.
