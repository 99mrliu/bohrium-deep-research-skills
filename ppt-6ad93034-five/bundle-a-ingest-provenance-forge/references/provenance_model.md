# Provenance model

The invariant of this skill: **any claim that reaches a slide must be
traceable, mechanically, to coordinates on a rendered page of the source
PDF.** This document defines the artifacts that carry that trace.

## 1. Span — the atomic unit (`work/spans.jsonl`)

One JSON object per line:

```json
{"span_id": "p2-s0008", "page": 2, "x0": 72.0, "y0": 557.25, "x1": 540.2,
 "y1": 568.25, "text": "AGS converges faster than the plain baseline ...",
 "method": "pdftotext-bbox", "reading_order": 14}
```

- `span_id` — stable within a run: `p<page>-s<seq>`; seq is extraction order
  on that page.
- `page` — 1-based PDF page number.
- `x0,y0,x1,y1` — bounding box in **PDF points, top-left origin**, exactly as
  emitted by `pdftotext -bbox-layout` (union of the line's word boxes).
  `null` in the `pdftotext -layout` fallback.
- `method` — `pdftotext-bbox` | `pdftotext-layout`. Anything else (e.g. a
  future OCR method) must be recorded here, never implied.
- `reading_order` — global index after multi-column re-serialization. On
  multi-column pages the order is column-major (left cluster top-to-bottom,
  then the next cluster); otherwise top-to-bottom, left-to-right.

Spans are **line-level**: words from one XHTML `<line>` are joined with single
spaces. Quotes that cross a line break must cite the consecutive spans and are
matched against their whitespace-normalized concatenation.

## 2. Render cross-validation (`work/pages/page-NNN.png`)

Every page is rendered at 150 dpi (`pdftoppm -r 150 -png`). These images are
the ground truth a human would see; the extracted text is a *hypothesis* about
them. When `ingest_report.json` flags an issue (U+FFFD, low yield, 1-char
storm), open the corresponding page render and compare before using any span
from that page. `paper.txt` (`[[page N]]` markers + spans in reading order) is
the quick text-side overview for the same purpose.

## 3. Figure zones (`work/figures.json`)

```json
{"fig_id": "fig-1", "caption": "Figure 1: Training loss ...",
 "caption_span_id": "p3-s0002", "page": 3,
 "zone_bbox_pdf": [36.0, 46.0, 576.0, 320.0],
 "crop_path": ".../work/figures/fig-1.png", "kind": "figure"}
```

- Captions match `^(Figure|Fig\.?|Table)\s*\d+` at span start.
- Zone heuristic (kept deliberately simple): the rectangle above the caption
  on the same page, from the bottom of the nearest text block above it
  (+4 pt) down to the caption top (−2 pt), spanning the full content width
  (36 pt margins). Crops are re-rendered with `pdftoppm -r 200 -x -y -W -H`;
  because both bbox coordinates and pdftoppm crop offsets are top-left
  origin, conversion is a pure `pt * dpi/72` scale.
- If the heuristic crops wrong, re-run with
  `--zone-override '{"fig-1":[x0,y0,x1,y1]}'` and inspect again.
- `kind: "table"` entries are never cropped; they carry the note "prefer
  native/CSV transcription".

## 4. Binding (`work/bindings.json`) — the fail-closed gate

The agent's `plan.json` cites evidence per bullet. `span_bind.py` verifies:

1. every `span_id` exists in `spans.jsonl`;
2. `quote` is a verbatim substring (whitespace-normalized) of the
   concatenation of its spans' texts;
3. every numeric token (`\d+(\.\d+)?%?`) in the bullet `text` occurs in the
   cited spans' text — this catches paraphrase-introduced numbers;
4. a slide-level `figure` id exists in `figures.json` (and, for figures, has
   a crop).

Output: per-bullet verdicts plus an `evidence_map` (bullet → span ids, pages,
quote, footer string). **Exit 1 on any failure — fix the plan, not the
checker.** `build_deck.py` re-checks `bindings.ok` and refuses to build
otherwise, so unverified content cannot reach the deck even if the agent
skips a step.

## 5. On-slide provenance

Each slide carries a footer line `p.<page> · spans <ids>` (and the same
string under each bullet in the body textbox), so the deck itself discloses
its evidence. Speaker notes come from the plan. `build_manifest.json` records
template handling, export status, and missing tools; `result.json` mirrors
the honest residual limits in `exceptions`.
