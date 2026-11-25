# Coordinate and source-location rules

## Page identity

Every image-bearing record has a stable source file identity, a unique `page_id`, and a zero-based `pdf_page_index`. `pdf_page_index` must be unique within the normalized source file identity, not across the whole atlas. `printed_page` is a separate nullable string read from the visible page, not calculated from the PDF index. Roman numerals, repeated supplement numbers, cover pages, and inserted plates must remain distinguishable. Supplemental PDFs have their own source identities and page-index sequences, so a main PDF and a supplement may both start at index 0.

## Image coordinates

Atlas bboxes use the original rendered image's full-page pixel coordinate system, including for crop records.

- Origin: top-left of the original full-page render.
- Axes: x increases rightward and y increases downward.
- Units: integer pixels.
- Encoding: `[x0, y0, x1, y1]`.
- Bounds: x0 and y0 are inclusive; x1 and y1 are exclusive.
- Validity: `0 <= x0 < x1 <= image.width` and `0 <= y0 < y1 <= image.height`.
- The page record supplies the exact render width and height. Coordinates from a differently scaled render or crop must be transformed back before recording.

A crop record may additionally identify a parent region, but the parent does not change this global convention. Never mix PDF points, percentages, crop-local pixels, printed-page numbers, and render pixels. The validator rejects nonnumeric, nonfinite, reversed, negative, out-of-image, and otherwise impossible bboxes.

## Region identity

Use unique region IDs independent of reading order. `kind` distinguishes figure, panel, caption, body_paragraph, table, table_row, table_column, and table_cell. `parent_id` links a panel to a figure or a row, column, or cell to a table. Parent and child must be on the same `page_id` in this compact schema; cross-page continuations use separate regions and a claim that names both.

Keep literal `panel_label`, `row_label`, and `column_label` fields when applicable. Empty or ambiguous labels are uncertainty, not permission to invent labels. Multi-page tables receive distinct cell IDs; their logical row/column identity should include continuation information.

## Source-text anchors

A `source_anchor` addresses the supplied UTF-8 text file by zero-based Unicode code-point offsets, with `start` inclusive and `end` exclusive. `quote` must equal `text[start:end]` exactly. End must equal start plus the Python length of quote. These anchors are checked deterministically against the supplied source text; a matching phrase at another location does not repair bad offsets.

Corroborated or conflicting caption/body states need an anchor. `not_reported` requires a null anchor. `missing` and `unreadable` can retain an anchor when its location is known. Extracted text coordinates are separate from image bboxes. Do not replace a bad source anchor with a filename or a generated quote.

## Reading order

A page declares its column count and `certain` or `uncertain` reading order. Multi-column pages must declare both. `uncertain` is rendered as an unresolved review item. Determining that two text blocks are adjacent in extraction does not determine their visual or semantic order.
