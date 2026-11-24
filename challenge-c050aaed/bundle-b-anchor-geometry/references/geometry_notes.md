# Geometry notes — anchor coordinate engineering

## 1. Coordinate origins: the one convention

**Every artifact in this skill uses page space with origin TOP-LEFT, y growing
DOWN.** This is what `pdftotext -bbox-layout` (`xMin/yMin/xMax/yMax`) and
PyMuPDF (`page.get_text("words")`, `annot.rect`, `annot.vertices`) already
produce, so normally nothing needs converting.

Raw PDF internals are different: the PDF default user space has origin
**bottom-left, y growing UP**. If you ever parse `/QuadPoints` or `/Rect`
directly (e.g. with pypdf), convert before writing the artifacts:

    y_top_left = page_height - y_pdf        (per coordinate)
    rect_tl    = [x0, page_height - y1, x1, page_height - y0]

Quad/rect and word boxes must live in the SAME space or every intersection is
garbage. When numbers look insane (negative y, y > page height), suspect a
missed conversion first.

## 2. Quad point order

PDF `/QuadPoints` are 8 numbers per quad: `x1 y1 x2 y2 x3 y3 x4 y4`
(conventionally upper-left, upper-right, lower-left, lower-right of the quad in
the annotation's space; viewers do not always honour the order).
**anchor_resolve.py reduces each quad to its axis-aligned bounding rect via
min/max of the 4 points, so point order is irrelevant to the algorithm.** A
multi-line highlight is a LIST of such quads, one per visual line segment.

## 3. Word-inside-quad rule (the single documented rule)

A word belongs to a quad iff

    area(word_box ∩ quad_rect) / area(word_box) > 0.5        (strict)

Exactly 0.5 is excluded. Rationale: majority-of-area is robust to quads that
slightly overshoot the visual selection (highlight padding), and the strict
inequality makes edge behaviour deterministic. anchor_verify.py deliberately
uses a DIFFERENT rule (word center inside rect) for the second pass, so the two
passes are independent: disagreement between them localizes drifted anchors.

## 4. Why two-column pages break serial extraction

Naive extractors dump page text in content-stream or row-major order. On a
two-column page that interleaves the columns line by line
(`left-line-1 right-line-1 left-line-2 right-line-2 ...`). Consequences:

* a quote that flows across the column break can never be found by substring
  search in the serial text;
* marked words joined in file order read in the wrong sequence (see
  examples/EXPECTED.md: the column-2 head sorts BEFORE the column-1 tail);
* bounding-box clipping over the full page width mixes both columns.

**Repair implemented here:** build the x-projection profile of all word boxes;
a zero-coverage band ≥ 8 units wide with covered words on both sides is a
column gutter (page margins are ignored because they have no words beyond
them). Assign each word to a column, group words into lines per column by
y-overlap, and sort `(column, line_y, x0)`. Multi-quad marks are concatenated
in quad order, which is the viewer's own reading-order signal. `column_count`
is recorded per anchor so downstream steps know the page layout.

## 5. OCR / scanned-page drift

When a PDF page has no text layer, word boxes come from an OCR engine and are
only approximately right. Typical drift causes:

* **skew / rotation** — small page rotation makes boxes shear; the recorded
  quad (from the annotating viewer, or re-derived) no longer aligns;
* **scale / DPI mismatch** — OCR at 150 DPI vs a 300 DPI render scales every
  coordinate;
* **baseline jitter** — per-line y shifts of a few pixels drop words out of a
  tight quad (the >0.5 rule then matches nothing or the wrong line);
* **token/character errors** — `rn`→`m`, `l`→`1`, merged/split tokens: the
  recorded quote differs from the OCR words even at the right location.

Mitigation pipeline: mark OCR words with `origin=ocr` + confidence in the TSV →
anchors on such pages get independently re-verified (drift shows up as
`drifted`/`failed`) → `drift_correct.py` slides difflib-scored windows of
n-1..n+1 words over the column-aware page sequence; a window scoring ≥ 0.75
against the recorded quote becomes the new anchor (`status=corrected`, old and
new bbox recorded); below 0.75 the anchor is honestly `unrecoverable` — the
text is never guessed.

## 6. FreeText / Ink marks

FreeText margin notes and Ink scribbles are NOT quotes of page text; they carry
meaning by position. They have no quads (or unusable ones), so they are
anchored to the **nearest text block** (line) by euclidean distance from the
mark rect center (`anchor_kind=nearest_block`, distance recorded). Their
`contents` is the note itself and must be kept as-is — drift_correct explicitly
skips them because fuzzy-matching a margin note against page text would be
meaningless.

## 7. Type / category / color preservation

`type` (Highlight/Underline/Squiggly/StrikeOut/FreeText/Ink...), `category`,
and `color_rgb` carry analytical meaning (e.g. red = disagreement, Squiggly =
doubt). The resolver copies the full input record verbatim and only ADDS
computed fields; nothing is merged into a single "annotation" bucket and no
color is quantized. Verification and correction preserve them the same way.

## 8. Determinism

All thresholds are fixed constants (overlap > 0.5, gutter ≥ 8, line tolerance
0.6 × median word height, difflib cut-offs 0.99/0.90/0.60, re-anchor ≥ 0.75).
Ties in the window search break to the first window in reading order. Same
inputs → byte-identical outputs.
