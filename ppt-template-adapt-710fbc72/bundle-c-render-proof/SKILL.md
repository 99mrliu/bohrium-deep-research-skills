---
name: render-proof-deck
description: Build an academic slide deck whose quality is proven against its own rendering — an automated export-audit-repair loop renders the deck to PDF, checks page parity, clipped or lost text, blank pages and font substitution on the rendered pages, repairs overflowing slides deterministically, and logs every iteration with file hashes, plus a whole-deck batch-consistency audit. Use when a presentation must survive real export (pptx→PDF/PNG) and stay uniform across all pages.
---

# Render-proof deck building (导出渲染 + 批量一致性方向)

This skill specializes in ONE problem: a deck is not done when the pptx
looks right in the editor — it is done when the *exported* PDF matches it
page by page, and when rules are applied uniformly to the whole deck. It
targets the failure modes "PDF fonts substituted / images lost / text
clipped at export", "only the first pages were fixed", and "nobody can
replay what happened". Content selection follows the paper; this skill owns
the render-truth half.

## Contract first

1. Read `/input/case.json` and `task.md`: `output_contract` fixes result
   field names; fixed audience / duration / slide count are binding. Work in
   `/app/work`, deliver to `/app/output` (deck, PDF, previews, reports,
   `result.json` with the original `case_id`). Save a valid partial result
   early; a partial result names its limits. Never fabricate paper content
   or render results — every claim about the render comes from a report file
   produced by these scripts.
2. Probe once and record: `python3 -c "import pptx"` (else `pip install
   python-pptx`), `soffice`/`libreoffice` or the runtime office-renderer,
   `pdftotext`/`pdftoppm`, CJK fonts (`fc-list :lang=zh`). If no renderer
   exists, the loop reports honestly and the delivery is `partial` — never
   claim an unverified export.

## Workflow (scripts under /skills/weekly-skill/scripts/)

### 1. Read the paper, plan pages

Extract text (`pdftotext -layout`), read the actual pages, and form the
mainline: question → method → results (one page per key figure/table) →
limitations. Allocate the fixed slide count. Keep one claim per slide: the
render loop *repairs* overflow by shrinking, but a slide that needs more
than two repair steps must be split — that is cheaper than a 12 pt wall of
text. Collect figure images at native resolution (200–300 dpi page-region
renders), each with caption and paper location. Write `plan.json` (schema in
`scripts/build_deck.py`'s docstring) with `body_pt` starting at 18.

### 2. Build (deliberately simple)

```
python3 scripts/build_deck.py --template /input/<template>.pptx \
    --plan /app/work/plan.json --out /app/output/deck.pptx \
    --report /app/output/build_report.json
```

The builder opens the real template so layouts inherit, fills title/body
placeholders, fits images with aspect ratio preserved, attaches notes. It
does no visual cleverness — visual truth is enforced in step 3 against the
rendering.

### 3. The render–audit–repair loop (core)

```
python3 scripts/render_loop.py /app/output/deck.pptx /app/output/export.pdf \
    --previews /app/output/previews --workdir /app/work \
    --out /app/output/render_report.json --max-iter 3
```

Each iteration exports the PDF (LibreOffice headless, private profile,
auto-retry on `DeploymentException`) and audits the **rendered pages**:
page count parity, blank pages, clipped words (bbox outside the page rect),
per-slide title presence, per-slide text coverage (every paragraph must
appear on its PDF page — whitespace-insensitive, because renderers insert
CJK autospacing), and the PDF font list. Slides with clipped/lost text get
all runs stepped −2 pt (floor 12 pt) and the loop re-renders; every
iteration is logged with the PDF's sha256, findings and repairs. The loop
exits clean, or writes a **per-page deviation table** into the report —
which must then appear in `result.json`'s uncertainty (the final check
enforces this). Font substitutions visible in the PDF font list are
recorded; if the theme font is missing, pick a metric-compatible installed
fallback, note it in the change log, and re-run the loop.

After the loop, **open the previews**: first page, densest page, last page.
The loop catches machine-checkable defects; overlaps and ugly wrapping need
your eyes. If you fix anything manually, re-run the loop.

### 4. Whole-deck batch consistency

```
python3 scripts/consistency_audit.py /app/output/deck.pptx \
    --pdf /app/output/export.pdf --duration-minutes <T> \
    --out /app/output/consistency.json
```

One rule set for every page: identical title band position, a coherent body
font histogram (ladder, not drift), no run below 12 pt, footer/slide-number
apparatus on all content slides or none (partial application fails), uniform
body left margin, notes on every slide with volume matching the talk budget,
and pptx↔PDF per-page text coverage at 100%. Fix all `fail`; justify any
`warn` in the change log.

### 5. Evidence map and honest result

Write `/app/output/evidence_map.json` (per slide: claim + sources with
kind/ref/pdf_page) and `/app/output/result.json`: original `case_id`, all
`output_contract` fields, honest status, artifact paths (deck, PDF,
previews, render_report, consistency report), sources with exact locations,
uncertainty (including the deviation table when the render is not clean),
and the change log (repairs applied by the loop, font fallbacks, export
retries, splits). Final gate:

```
python3 scripts/final_check.py --case /input/case.json \
    --result /app/output/result.json \
    --render-report /app/output/render_report.json --base /app \
    --out /app/output/final_check.json
```

It refuses delivery when contract fields are missing, artifacts are absent,
or a non-clean render is not disclosed in the uncertainty.

## Failure handling

| Situation | Action |
|-|-|
| Loop fails after max iterations on one slide | Split the slide's content, rebuild, re-run the loop |
| `page_parity` / `blank_page` findings | Structural export problem, not font-repairable — inspect the preview, rebuild the offending slide |
| LibreOffice `DeploymentException` | Auto-retried with fresh profile; persistent failure → `partial` with the failed iteration logs |
| Font substitution in PDF font list | Metric-compatible fallback + change-log entry + re-run loop |
| CJK text missing in export | Environment lacks CJK fonts — install/locate via font-discovery, re-run |
| Apparatus (footer/page number) on some slides only | Apply to all content slides (clone from layout) or remove everywhere; re-audit |
| Renderer absent | Deliver pptx + reports as `partial`; say the export is unverified |

## Minimal invocation example (illustrative, not an official case result)

Input: `paper.pdf`, `template.pptx`, "10 slides, 12 minutes". Sequence:
plan → `build_deck.py` → `render_loop.py --max-iter 3` →
`consistency_audit.py --pdf export.pdf --duration-minutes 12` →
evidence_map + result.json → `final_check.py`. Illustrative loop output:
`iter 1: 2 findings, 1 repairs; iter 2: 0 findings` → `pass`, with
`render_report.json` recording both iterations and the final PDF hash.

## Limits

Text-coverage uses whitespace-insensitive substring matching — it catches
lost/clipped text, not paraphrase drift (that is your reading job). Blank-
page detection is text-based; a page of pure images needs the previews.
Repair by shrinking stops at 12 pt — beyond that, split the slide.
