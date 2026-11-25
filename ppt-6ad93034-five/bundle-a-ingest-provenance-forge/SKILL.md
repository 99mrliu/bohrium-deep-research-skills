---
name: ingest-provenance-forge
description: Forensic PDF ingest layer for academic slide decks: every text span carries coordinate-level provenance (page, bbox, extraction method), render cross-validation catches garbled extraction, and slide bullets may only reference verified span ids (fail-closed binding). Trigger on 学术 PPT 生成与编辑 tasks — turning a research paper PDF plus a slide work order into an editable deck where factual traceability matters. Boundary: the deck builder is deliberately minimal (pure-stdlib PPTX); full template theme inheritance is out of scope and declared in exceptions.
---

# ingest-provenance-forge

## Philosophy

The center of gravity of this skill is **upstream data truthfulness at the PDF
boundary**. Most paper-to-slides failures are not design failures; they are
ingest failures: garbled glyphs, two-column text read across columns, numbers
hallucinated because nobody checked them against the page. So this skill spends
its complexity budget on a forensic ingest layer — coordinate-level spans,
render cross-validation, multi-column re-ordering, extraction forensics — and
on a **fail-closed binding gate**: no bullet reaches the deck unless every
span id exists, its quote is verbatim, and every numeric token is found in the
cited spans. The deck builder downstream is deliberately minimal; a plain deck
with verified content beats a beautiful deck with unverifiable claims.

## Runtime contract

- The skill is installed at `/skills/weekly-skill`. Original inputs are under
  `/input`: `case.json`, `task.md`, the paper PDF, usually
  `target-template.pptx`, optionally `starting-deck.pptx` and
  `artifacts/slide-workorder.json`. Read the REAL files; never assume content
  from labels.
- Work under `/app/work`; final deliverables under `/app/output`:
  `presentation.pptx` (editable), `presentation.pdf` + preview PNGs when an
  office renderer (`soffice`) exists, evidence/provenance map, check report,
  and `result.json`.
- `result.json` MUST contain the original `case_id` (from case.json: key
  `case_id` or `id`) and EVERY root field of the case's `output_contract`
  (read it from case.json; if absent use defaults: `status`,
  `editable_source`, `export_artifact`, `content_map`, `compliance_checks`,
  `exceptions`). `status` ∈ `success|partial|unable_to_determine|refused`; a
  `partial` must state its limits precisely. Secure a partial result.json
  EARLY, improve in place. Never fabricate paper content, numbers, fonts or
  tool results; honest uncertainty goes to `exceptions`.
- Scripts are invoked as `python3 /skills/weekly-skill/scripts/<name>.py`.
  Every script takes CLI flags and/or env vars `CASE_INPUT_DIR`,
  `CASE_WORK_DIR`, `CASE_OUTPUT_DIR` (defaults `/input`, `/app/work`,
  `/app/output`) so the same code runs in the example. Pure Python 3 stdlib
  only for core logic. Optional tools are detected with `shutil.which`:
  `pdftotext`, `pdftoppm`, `soffice`/`libreoffice`; degrade gracefully and
  record what was missing. No network access.

## Workflow

1. **Secure the partial result** (before anything can fail silently):
   ```bash
   python3 /skills/weekly-skill/scripts/result_make.py --status partial \
     --exception "ingest not yet complete"
   ```
2. **Forensic ingest** — renders pages, extracts coordinate spans, detects
   multi-column pages, writes `spans.jsonl`, `paper.txt`, `ingest_report.json`:
   ```bash
   python3 /skills/weekly-skill/scripts/pdf_ingest.py --pdf /input/<paper>.pdf
   ```
   Read `ingest_report.json` issues BEFORE trusting any text. Cross-check a
   few spans against `pages/page-NNN.png`.
3. **Figure zones** — locate caption zones, crop figure regions:
   ```bash
   python3 /skills/weekly-skill/scripts/figure_zones.py
   ```
   Inspect `figures.json` and the crops; if a zone is wrong, re-run with
   `--zone-override '{"fig-1":[x0,y0,x1,y1]}'` (PDF pt, top-left origin).
4. **Write the plan** (agent-authored) at `$CASE_WORK_DIR/plan.json`:
   `{"slides":[{"id","title","bullets":[{"text","span_ids":[...],"quote":"verbatim substring"}],"notes","figure":optional}]}`
   — every bullet must cite the span ids it paraphrases and quote them
   verbatim; the quote must really occur in those spans.
5. **Fail-closed binding, then build**:
   ```bash
   python3 /skills/weekly-skill/scripts/span_bind.py --plan $CASE_WORK_DIR/plan.json
   python3 /skills/weekly-skill/scripts/build_deck.py --plan $CASE_WORK_DIR/plan.json \
     --bindings $CASE_WORK_DIR/bindings.json [--template /input/target-template.pptx]
   ```
   `span_bind` exits 1 on any failure — fix the plan, not the checker.
   `build_deck` refuses to build on failed bindings; with `soffice` present it
   also exports `presentation.pdf` and `preview/` PNGs.
6. **Finalize the result** (upgrade the early partial in place):
   ```bash
   python3 /skills/weekly-skill/scripts/result_make.py --status success \
     --set-json 'editable_source="/app/output/presentation.pptx"' \
     --check spans_verified=true --exception "<any remaining limit>"
   ```

## Exception handling

| Situation | Behavior |
|---|---|
| Image-only PDF / page (chars/page < 200 or empty page) | `ingest_report.json` issue recommends OCR or crop-embed; treat text as untrusted, keep status `partial` and say so |
| `pdftotext` missing | spans may be absent or layout-only (bbox:null); ingest exits 2, record missing tool, status `partial` |
| `-bbox-layout` parse fails | automatic fallback to `pdftotext -layout` line spans (bbox:null); figure zoning disabled, declared in report |
| Figure crop wrong | re-run `figure_zones.py --zone-override '{"fig-1":[x0,y0,x1,y1]}'`; never ship an uninspected crop |
| Quote fails binding / numeric token absent | `span_bind` exits 1 with the exact reason; **fix the plan, not the checker** |
| `bindings.json` not ok | `build_deck` refuses (exit 1); the deck is never built on unverified content |
| Template theme | only slide size (`sldSz`) is adopted from `--template`; full theme inheritance is out of scope and declared in the manifest + exceptions |
| `soffice` missing | PDF export and previews skipped gracefully, recorded in `build_manifest.json` and `result.json` exceptions |
| Tables | detected but never cropped as images; marked "prefer native/CSV transcription" |

## Scripts

- `scripts/pdf_ingest.py` — forensic ingest: page renders, coordinate spans
  (`spans.jsonl`), multi-column reading order, extraction forensics
  (`ingest_report.json`), linearized `paper.txt` with `[[page N]]` markers.
- `scripts/figure_zones.py` — caption detection (`^(Figure|Fig\.?|Table)\s*\d+`),
  zone rectangles, `pdftoppm` crops to `figures/fig-<n>.png`, `figures.json`.
- `scripts/span_bind.py` — fail-closed verifier: span ids exist, quote is a
  verbatim substring, numeric tokens occur in cited spans, figure ids exist;
  writes `bindings.json` with verdicts and an evidence map; exit 1 on failure.
- `scripts/build_deck.py` — pure-stdlib minimal PPTX writer (16:9; adopts
  template slide size); embeds figure crops; per-bullet footer
  `p.<page> · spans <ids>`; speaker notes; optional soffice PDF export +
  previews; writes `build_manifest.json`.
- `scripts/result_make.py` — early-partial / final `result.json` writer;
  copies every `output_contract` root field verbatim, merges in place.

## Minimal example (synthetic)

`examples/` contains a **fully synthetic** 3-page paper (all content
fabricated, ASCII-only, generated by `make_fixture.py` with a stdlib PDF
writer) and runs the whole chain end to end. It is NOT an official case
result; every artifact carries a synthetic marker. Run it with:

```bash
cd examples && bash run_example.sh
```

See `examples/expected_output.md` for the expected artifact list and the
deliberately-failing binding variant.
