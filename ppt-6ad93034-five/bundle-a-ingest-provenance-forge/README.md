# ingest-provenance-forge

**Forensic PDF ingest with fail-closed provenance binding for academic slide
decks (学术 PPT 生成与编辑).**

## What

A skill bundle that turns a research paper PDF + a slide work order into an
editable academic PPTX — with one unusual guarantee: **every bullet on every
slide is bound, fail-closed, to coordinate-level text spans extracted from the
paper itself.** Each span carries `{page, bbox, extraction method}`; pages are
also rendered to images so extraction can be cross-validated against what a
human would see; a binding verifier refuses (exit 1) any bullet whose quote is
not a verbatim substring of its cited spans or whose numbers do not occur in
them; and the deck builder refuses to build on failed bindings.

## Why

Most paper-to-slides errors are ingest errors, not design errors:

- two-column PDFs read across columns → scrambled sentences,
- broken font encodings → U+FFFD / CID garbage that looks like text,
- image-only pages → silently empty extraction,
- LLM-authored bullets → plausible numbers that never occurred in the paper.

This bundle spends its complexity budget upstream, at the PDF boundary, and
keeps the deck builder deliberately minimal (pure-stdlib PPTX writer; template
theme inheritance out of scope).

## How (architecture)

```
paper.pdf ──► pdf_ingest.py ──► spans.jsonl (page,bbox,method,reading_order)
                 │              ingest_report.json (forensics + issues)
                 │              paper.txt ([[page N]] markers)
                 │              pages/page-NNN.png (render cross-validation)
                 ▼
          figure_zones.py ──► figures.json + figures/fig-N.png crops
                 ▼
   agent plan.json ──► span_bind.py ──► bindings.json (verdicts+evidence map)
                 │                     exit 1 on ANY failure
                 ▼
          build_deck.py ──► presentation.pptx (+pdf/previews if soffice)
                 ▼
          result_make.py ──► result.json (early partial, upgraded in place)
```

- **Pure Python 3 stdlib** for all core logic (including the PPTX writer).
- Optional external tools are auto-detected via `shutil.which` and degrade
  gracefully: `pdftotext` (spans), `pdftoppm` (renders/crops),
  `soffice`/`libreoffice` (PDF export). No network access.
- All scripts accept `CASE_INPUT_DIR` / `CASE_WORK_DIR` / `CASE_OUTPUT_DIR`
  env vars (defaults `/input`, `/app/work`, `/app/output`).

## Quickstart

```bash
# the fully synthetic end-to-end demo (needs poppler; no soffice required)
cd examples && bash run_example.sh
```

On a real case (skill installed at `/skills/weekly-skill`):

```bash
python3 /skills/weekly-skill/scripts/result_make.py --status partial
python3 /skills/weekly-skill/scripts/pdf_ingest.py --pdf /input/paper.pdf
python3 /skills/weekly-skill/scripts/figure_zones.py
# ... author $CASE_WORK_DIR/plan.json citing real span ids ...
python3 /skills/weekly-skill/scripts/span_bind.py --plan $CASE_WORK_DIR/plan.json
python3 /skills/weekly-skill/scripts/build_deck.py \
  --plan $CASE_WORK_DIR/plan.json --bindings $CASE_WORK_DIR/bindings.json \
  --template /input/target-template.pptx
python3 /skills/weekly-skill/scripts/result_make.py --status success \
  --set-json 'editable_source="/app/output/presentation.pptx"'
```

## Example outputs (synthetic demo)

| Artifact | Proves |
|---|---|
| `work/work/spans.jsonl` | every span has page + bbox + method + reading order |
| `work/work/ingest_report.json` | extraction forensics ran (issues[] would list U+FFFD, empty pages, low yield, 1-char storms) |
| `work/work/figures/fig-1.png` | caption-zone crop of the paper's own figure region |
| `work/work/bindings.json` | all 5 bullets verified fail-closed (`"ok": true`) |
| `work/app-output/presentation.pptx` | valid editable deck (opens in python-pptx; title prefixed `SYNTHETIC EXAMPLE — `) |
| `work/app-output/result.json` | `case_id` + all six `output_contract` fields, `"synthetic_example": true` |

## Limitations

- The PPTX writer is intentionally minimal: absolute-positioned text boxes,
  one blank layout, one minimal theme. `--template` adopts only the slide
  size (`sldSz`); **full theme inheritance is out of scope**.
- No OCR: image-only pages are *detected* and flagged (recommend OCR or
  crop-embed), not transcribed.
- Tables are detected but never cropped; they are marked "prefer native/CSV
  transcription".
- Coordinate space is the one emitted by `pdftotext -bbox-layout` (points,
  top-left origin); figure zoning relies on it and is disabled in the
  `-layout` fallback.
- The multi-column detector is a simple x0-clustering heuristic; exotic
  layouts (figures interleaved with text columns) may need
  `--zone-override` for crops and manual reading-order review.

## Repository layout

```
skill/
├── SKILL.md                  # agent-facing skill definition
├── README.md                 # this file
├── GITHUB_URL.txt
├── scripts/                  # the machinery (stdlib-only core)
├── references/               # provenance model + PDF failure modes
└── examples/                 # runnable synthetic end-to-end demo
```
