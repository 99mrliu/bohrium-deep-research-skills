---
name: evidence-locked-deck
description: Build an academic slide deck under an evidence gate — every content slide must cite verbatim source anchors that a script verifies against the actual paper text before building, every number on the slides is audited against the source, and each slide carries a visible source line plus speaker notes keyed to the same citations. Use when a paper must be turned into a traceable, non-hallucinated presentation with a page-level evidence map.
---

# Evidence-locked deck building (论文主线 + 图表引用 + 可核验方向)

This skill specializes in ONE problem: nothing enters the deck unless it is
anchored to the actual source, and the anchoring is machine-checked, not
self-declared. It targets the failure modes "page content doesn't match the
paper", "figure numbers and citations drift", and "numbers get invented".
Template fitting is deliberately kept simple and safe; the evidence pipeline
is the contribution.

## Contract first

1. Read `/input/case.json` and `task.md`: `output_contract` fixes result
   field names; fixed audience / duration / slide count are binding; the
   task's source and uncertainty rules override everything below. Work in
   `/app/work`, deliver to `/app/output` (deck, PDF, previews, reports,
   `result.json` with the original `case_id`). Save a valid partial result
   early. Never fabricate paper content, anchors, or check outcomes.
2. Probe once, record in the change log: `python3 -c "import pptx"` (else
   `pip install python-pptx`), `pdftotext`/`pdftoppm`/`pdfimages` (else
   PyMuPDF), a renderer (`soffice` or the runtime office-renderer), and the
   ocr tool for text-layer-empty PDFs.

## Workflow (scripts under /skills/weekly-skill/scripts/)

### 1. Index the source — the only ground truth

```
python3 scripts/extract_source.py --pdf /input/<paper>.pdf \
    [--figures-dir /input/figures] --out /app/work/source_index.json
```

You get per-page text, detected section headings, an image inventory per
page, and sha256 of every input. If the text layer is mostly empty the
script says so: re-render pages and OCR, and mark every anchor derived from
OCR as `unverified`-grade evidence. Distinguish PDF page numbers from
printed page numbers and use PDF pages everywhere. Read the index — never
write slide content from memory or from file names.

### 2. Draft claims with verbatim anchors, then pass the gate

While reading, draft `claims.json`: the candidate slide claims, each with
`kind` (figure/table/section/equation/text), the source-native `ref`
(`Fig. 3`, `Table 2`, section number), `pdf_page`, and an `anchor` — a short
**verbatim** quote copied from the extracted text. Then:

```
python3 scripts/verify_anchors.py --index /app/work/source_index.json \
    --claims /app/work/claims.json --out /app/work/claims.verified.json --fuzzy
```

The gate verifies each anchor as an exact normalized substring on the cited
page (or ≥ 0.8 token overlap with `--fuzzy`, for quotes broken across lines).
`page_mismatch` means the evidence exists on another page — fix the page,
keep the claim. `unverified` means the claim has no support: rewrite it from
the actual text or drop it. Exit code 1 blocks the pipeline until every
claim you will use verifies.

### 3. Plan pages from verified claims only

Form the mainline — question, method, results (each keyed to a verified
figure/table claim), limitations — and allocate the fixed slide count:
cover, optional outline, background/question, method, one results page per
key figure/table, limitations, conclusion. Write `plan.json` (schema in
`scripts/build_deck.py`'s docstring); each content slide's `evidence` list
copies the *verified* entries from `claims.verified.json`. Speaker notes say
what to say per slide (~240 Chinese chars or 140 English words per minute of
the slot); the builder appends the source line automatically.

### 4. Build (the gate runs again)

```
python3 scripts/build_deck.py --template /input/<template>.pptx \
    --plan /app/work/plan.json --out /app/output/deck.pptx \
    --evidence-map /app/output/evidence_map.json \
    --report /app/output/build_report.json
```

The builder refuses to build a deck whose content slides lack verified
evidence (default strict mode). It opens the template itself so layouts
inherit, fills title/body placeholders, inserts figures with aspect ratio
preserved, prints a `来源: Table 2 (p.8); …` line on each slide, mirrors it
into the notes, and emits `evidence_map.json`. Read and resolve every
warning.

### 5. Audit numbers against the source

```
python3 scripts/check_numbers.py --deck /app/output/deck.pptx \
    --index /app/work/source_index.json --out /app/output/numbers_check.json \
    --allow "<deck-internal integers, e.g. slide counts, years>"
```

Every numeric token on every slide must appear in the source text (format
variants normalized). Unmatched numbers are hallucinations or typos: fix the
slide or justify the number in the change log. Keep `--allow` minimal and
record why each entry is deck-internal.

### 6. Export, verify rendering, inspect

```
python3 scripts/export_render.py /app/output/deck.pptx /app/output/export.pdf \
    --previews /app/output/previews --out /app/output/export_report.json
```

Page count must equal slide count; each slide's title is spot-checked on its
own PDF page; previews render for every page. **Look at the first, densest
and last previews.** Font substitution or export retries are recorded in the
report and must be echoed in the change log.

### 7. Honest result + final gate

Write `/app/output/result.json`: original `case_id`, all `output_contract`
fields, honest status, artifact paths, sources with exact locations
(pdf page + ref), `uncertainty` (every anchor left unverified, OCR doubts,
missing figures), and the change log. Then:

```
python3 scripts/contract_check.py --case /input/case.json \
    --result /app/output/result.json --deck /app/output/deck.pptx \
    --evidence-map /app/output/evidence_map.json --base /app \
    --out /app/output/contract_check.json
```

It fails unless the contract fields exist, artifacts are on disk, and the
evidence map covers every slide.

## Failure handling

| Situation | Action |
|-|-|
| Anchor unverified after rewriting | Drop the claim or present it explicitly as unsupported; list under uncertainty |
| `page_mismatch` | Correct `pdf_page` to the page where the anchor matched |
| Text layer empty / garbled | Re-render + OCR; downgrade affected anchors; note in uncertainty |
| Figure file missing or unusable | Re-render the PDF page region at 200–300 dpi; never invent the figure |
| Unmatched number | Fix from source, or remove; `--allow` only provably deck-internal numbers |
| Export crash | Handled with profile retry; if still failing, deliver pptx + report as `partial` |
| Template lacks body placeholder | Builder substitutes an aligned text box and logs the substitution |

## Minimal invocation example (illustrative, not an official case result)

Input: `paper.pdf`, `template.pptx`, "10 slides, 12 min, journal club".
Sequence: `extract_source.py` → draft 15 claims → `verify_anchors.py --fuzzy`
(13 verify, 2 dropped) → plan 10 slides from the 13 → `build_deck.py` →
`check_numbers.py` → `export_render.py` → `result.json` →
`contract_check.py`. Illustrative gate output: `verified: 13/15`, and the
built deck's slide 6 shows `来源: Table 2 (p.8)` under a results table whose
`28.4` passes the numeric audit.

## Limits

Anchor verification proves the quote exists on the cited page, not that the
claim interprets it correctly — reading remains your job. The numeric audit
cannot catch wrong units or swapped labels. Rendering checks are spot
checks; the previews are the final arbiter.
