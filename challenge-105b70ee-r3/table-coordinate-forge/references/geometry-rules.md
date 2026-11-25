# Coordinate reconstruction and review rules

## 1. Source of truth and prohibited shortcuts

The source order is:

1. Original PDF page and task field definition.
2. `pdftotext -bbox-layout` page/word coordinates generated from that PDF.
3. Reconstructed physical rows, gutters, cells, and continuation links.
4. Reviewed semantic binding to a requested field.

Never run this direction backwards from a field keyword to a convenient number.
Never repair text, join hyphenated prose, normalize Unicode, convert comma decimal
separators, strip uncertainty notation, or substitute a domain dictionary. Word
text is retained exactly as XML-decoding supplies it; inserted single spaces only
separate token boxes within a cell.

Coordinates use the units supplied by Poppler, normally PDF points, with the
origin at the upper-left. `page` in evidence is the one-based page sequence;
`pdf_page_label` separately preserves the XHTML page-number string.

## 2. Physical line recovery

For each page:

1. Parse XHTML with `xml.etree.ElementTree`, namespace-independently.
2. Require numeric page width/height and word `xMin`, `yMin`, `xMax`, `yMax`.
   Reject malformed coordinates and inverted boxes; do not guess replacements.
3. Keep block and line identities in stable word and source-line IDs.
4. Sort lines by vertical center, then x. Merge lines considered to share a
   baseline only if their vertical centers differ by at most half the larger
   height and their vertical overlap is at least half the smaller height.
5. Sort merged words by x and retain the union box. No y-sorting is used within a
   cell, because this implementation does not stack wrapped lines automatically.

A stable ID has the form `s001-p001-b001-l001-w001`; a physical row has a separate
`s001-p001-pr001` ID. These are generated coordinate identifiers, not official
paragraph numbers from a publisher.

## 3. Candidate table runs

Within a physical row, adjacent word boxes become one group until horizontal
whitespace is at least:

```text
max(8.0 coordinate units, 0.65 × median word height in that row)
```

The threshold is geometric, not based on keywords or scientific vocabulary.
Each group retains its own words, text, box, and calculated threshold.

A candidate run is a maximal sequence of consecutive physical rows having at
least two groups. A run needs at least two rows. A one-group caption ends a run;
a one-group table footnote is not automatically attached. This conservative rule
prevents most prose paragraphs from becoming tables, but repetitive prose can
still form false candidates and visual borders alone are invisible here.

## 4. Repeated-gutter columns

For every adjacent pair of groups in every candidate row, record the intervening
horizontal gap and its row. Cluster gaps when their intervals overlap or centers
differ by at most:

```text
max(3.0 coordinate units, 0.5 × median row height)
```

A cluster is admissible only when it contains gaps from at least two distinct
rows. Its median gap center becomes a column cut. Near-duplicate centers within
the same tolerance are deduplicated, keeping the center with the greatest row
support. A candidate without a repeated cut is not emitted as a table; more than
30 cuts is rejected as unstable.

With `n` accepted cuts, the grid has `n + 1` columns. `column_cuts` stores original
coordinates and `relative_column_cuts` divides them by page width for cross-page
comparison. `cut_row_support` exposes how many rows supported each cut, allowing a
reviewer to reject weak column geometry.

This handles left-, right-, and center-aligned cells better than left-edge
clustering because cuts arise from whitespace rather than character starts.
Nevertheless, unusually spaced prose, mathematical formulas, large column shifts,
or long text across a shared gutter can create wrong cuts.

## 5. Cells, blanks, and spanning geometry

For each coordinate group:

- cuts to the left of its x-minimum determine its starting column;
- cuts inside the group box make it a spanning group;
- cuts at or beyond its x-maximum end its occupied range.

Groups assigned exactly the same range are merged in x order. A nonblank cell
stores its complete coordinate text, occupied `column_start`/`column_end`, all word
IDs, page, source, and `spanning_geometry=true` when it crosses a cut. Uncovered
single columns receive an explicit blank cell with `text=null` and no word IDs.

A spanning cell is marked `c01-c03` rather than split into invented copies. This
is an observation that a group crossed candidate cuts, not a publisher-certified
colspan. If two groups overlap a column ambiguously, do not select a value from
the affected region without visual review. Blank cells can never be reported as
zero or scalar values.

Paragraph evidence uses the stable cell ID, for example
`s001-seg002-r02-c03`. This ID reconstructs source → page → table segment →
physical row → occupied column(s). Coordinates remain available in `tables.json`.

## 6. Header representation

The first physical row of each segment is emitted as `header_row_ids[0]` and all
remaining rows as geometric data-row candidates. Every segment carries:

```text
header_status = geometric_candidate_requires_agent_review
```

The script does not infer that a first row is semantically a heading merely
because it is first. The agent must inspect it. Later header rows or hierarchical
headings are not auto-merged; if extra header cells are used as condition evidence,
their exact text is checked, but complex hierarchies may require an extension.

For each column, `header_cell_ids_by_column` records an ordered path of inherited
and current-page header candidates. This is the important distinction from a
plain text table: page-2 values can retain page-1 headings even when the repeated
heading says only “continued,” and they can retain both old and new evidence.

## 7. Continued table decision

Only the last viable segment on one source page can join the first viable segment
on the immediately following page of the **same source**. Different documents do
not continue one another. Equal column count is mandatory.

For comparison only, a temporary copy of header text lowercases ASCII/case-aware
text and removes recognized continuation markers (`continued`, `cont.`, and
`续表`, with optional surrounding brackets). This temporary comparison never
rewrites a stored cell or emitted quote.

Join a segment when either:

1. the new header contains an explicit continuation marker and all corresponding
   relative cuts differ by at most 0.10; or
2. normalized-header sequence similarity is at least 0.65 and every relative cut
   differs by at most 0.04.

Store `continued_from`, a human-readable reason, rounded similarity, and cut delta.
Otherwise start a new table; never join solely because two pages both contain
three columns. When joined, concatenate each inherited header path with current
own header candidates. The reviewer must include the needed inherited/current
headers explicitly in the binding.

Explicit markers do not override different sources, nonadjacent pages, changed
column count, or grossly incompatible geometry. Continuation without a repeated
header is not auto-accepted by this version; keep affected fields under review.

## 8. Required visual-review triggers

Inspect the original PDF especially when any condition holds:

- cell text is split across lines or logical records occupy multiple physical rows;
- text crosses a cut, cells overlap, or blank cells appear unexpectedly;
- the first row is data, multiple header rows exist, or a row label appears alone;
- only one cut or two rows supports a table-shaped region;
- units occur in a separate note, symbol row, caption, or spanning footer;
- page rotation, landscape layout, nested tables, images, or formulas are present;
- a needed continuation link is missing or the normalized match was marginal;
- two sources supply different scalar text for the same field conditions.

If unresolved, use `extraction_failed` with the page/segment and precise obstacle;
do not force candidate geometry into a polished-looking result.

## 9. Preview inspection

`table-preview.md` is the fastest semantic review surface. It displays every cell
and its ID plus the effective header path. `table-preview.svg` uses only SVG text,
line, and rectangle elements; values and IDs remain searchable without an image
library. Long SVG cell text is visibly truncated at 44 characters for layout, so
`tables.json` is authoritative for the full quote. Markdown escapes pipes only for
rendering and likewise does not redefine the cell value.

A preview that “looks right” still does not promote any answer. Promotion occurs
only after an explicit binding passes exact text/header checks in
`answer_forge.py` and the complete output validator.
