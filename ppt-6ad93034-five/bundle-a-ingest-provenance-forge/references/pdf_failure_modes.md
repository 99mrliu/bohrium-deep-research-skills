# PDF failure modes at the ingest boundary

What goes wrong when you treat `pdftotext` output as truth, and what this
skill does about it. Rule of thumb: **extracted text is a hypothesis; the
rendered page is the evidence.**

## 1. Garbled glyphs / broken encodings

Symptoms: U+FFFD replacement characters, control characters in words, or
pages where most "lines" are single characters (CID-keyed fonts with a broken
ToUnicode map — typical for some CJK papers and old LaTeX dvips output).

Detection in `ingest_report.json`: `replacement-char`, `control-chars`,
`font-encoding-anomaly` (>20% 1-char spans on a page with ≥10 spans).

Action: do NOT quote affected spans into slides. Cross-check
`pages/page-NNN.png`; if the render is fine, the content may only be used as
an image crop (or via OCR, which is out of scope here — declare it in
exceptions and keep status `partial`).

## 2. Image-only pages / low text yield

Scanned papers, or pages where all content is one big bitmap, extract as
empty or near-empty pages.

Detection: `empty-page` (no spans) and `low-text-yield` (<200 chars/page).

Action: flag for OCR or crop-embed; never invent the missing text. A deck
built over an image-only paper is `partial` by definition unless every claim
is backed by a crop.

## 3. Multi-column reading order

Naive top-to-bottom serialization interleaves left and right columns,
producing fluent-looking garbage — the most dangerous failure because nothing
"looks" wrong.

Detection: cluster span `x0` per page; if 2+ clusters (gap > 40 pt, ≥3 spans
each) overlap vertically by >50%, the page is flagged `multi-column` and
reading order is re-serialized column-major (`reading_order` per span).

Action: trust `reading_order`, not extraction order; verify a paragraph in
`paper.txt` reads coherently before quoting it.

## 4. Coordinates you can't trust

Different tools use different origins (PDF bottom-left vs. image top-left)
and units (pt vs. px vs. EMU). Mixing them produces crops of the wrong
region — usually silently.

Policy: this skill standardizes on `pdftotext -bbox-layout` coordinates
(points, **top-left** origin). pdftoppm crop offsets are also top-left, so
zone→crop conversion is a pure dpi scale — no flip. If you ever import
bottom-left boxes (PyMuPDF raw dicts, PDF operators), flip y first. If bbox
extraction fails entirely, the `-layout` fallback yields `bbox: null` spans:
text may still be quoted, but figure zoning is disabled and the report says
so.

## 5. Hallucinated numbers downstream

Even with perfect ingest, an LLM writing bullets will occasionally
"remember" 95.1% where the paper says 92.3%.

Policy: the fail-closed gate. Every bullet cites `span_ids` + a verbatim
`quote`; every numeric token in the bullet text must occur in the cited
spans. Failure exits 1 and blocks the build. The checker is never edited to
make a plan pass — the plan is fixed, or the claim is dropped to
`exceptions`.

## 6. Silent tool absence

A pipeline that silently skips rendering or export produces half-artifacts
that look complete.

Policy: every script detects optional tools with `shutil.which`, records
missing ones (`ingest_report.json`, `build_manifest.json`,
`result.json.exceptions`), and degrades: no pdftoppm → no renders/crops; no
pdftotext → exit 2 partial; no soffice → no PDF export, deck still delivered.
