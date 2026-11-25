---
name: table-rebind-lab
description: Mine printed tables from a research-paper PDF into provenance-carrying CSVs, rebuild them as NATIVE editable pptx tables, and replot charts from those CSVs verbatim with in-chart source notes; bitmap figures are embedded only as visually-verified crops (pixel values are never estimated). A fail-closed number audit binds every number on every slide to the paper text or a CSV before the deck is built. For 学术 PPT 生成与编辑 figure/table tasks (官方方向3: 图表插入); boundary: does not OCR scanned PDFs, does not transcribe numbers from bitmap charts, and does not inherit full template themes (slide size only).
---

# table-rebind-lab

## Philosophy

**A number on a slide is either bound to a printed source or it does not
appear.** Tables are mined from the PDF text layer into CSVs that carry their
caption and page; slides get *native* `<a:tbl>` tables and *replotted* charts
from those CSVs — never screenshots of tables, never values eyeballed from a
bitmap. Editable-native beats screenshot: the evaluator must be able to click
into the table and change a cell. Bitmap figures travel only as crops whose
zone was verified by an actual rendered image, with the original caption
re-attached. Before any deck is built, a fail-closed audit checks every
numeric token, every `Figure N`/`Table N` mention, every ref, and every unit.
If the audit fails, you fix the plan — never the checker.

## Runtime contract

- The skill is installed at `/skills/weekly-skill`. Scripts are invoked as
  `python3 /skills/weekly-skill/scripts/<name>.py`. Pure-stdlib core; no
  network. `pdftotext` / `pdftoppm` / `soffice` are detected via
  `shutil.which` and degrade gracefully. `matplotlib` is OPTIONAL: without it,
  `replot.py` exits 3 — deliver native tables + crops and note the exception.
- Original inputs live under `/input`: `case.json`, `task.md`, the paper PDF,
  usually `target-template.pptx`, optionally `starting-deck.pptx` and
  `artifacts/slide-workorder.json`. **Read the real files; never assume.**
- Work under `/app/work`; deliverables under `/app/output`:
  `presentation.pptx` (editable, native tables), `presentation.pdf` +
  `preview/` when `soffice` exists, `tables/` CSVs, `charts/` PNGs +
  provenance, `number_audit.json`, `result.json`.
- `result.json` MUST contain the original `case_id` (`case.json` key
  `case_id` or `id`) and EVERY root field of the case's `output_contract`
  (defaults if absent: `status`, `editable_source`, `export_artifact`,
  `content_map`, `compliance_checks`, `exceptions`). `status` ∈
  `success | partial | unable_to_determine | refused`; `partial` states its
  limits precisely. **Secure a partial `result.json` EARLY** (before the heavy
  steps) and finalize it at the end.
- Env vars `CASE_INPUT_DIR`, `CASE_WORK_DIR`, `CASE_OUTPUT_DIR` (defaults
  `/input`, `/app/work`, `/app/output`).
- Never fabricate data. Never estimate values from bitmap pixels.

## Workflow (≤ 6 steps)

```bash
S=/skills/weekly-skill/scripts
# 0. Secure an early partial result BEFORE heavy work (survives any crash):
python3 $S/result_make.py --case /input/case.json --out /app/output/result.json \
    --status partial --exception "run in progress: early partial secured"
# 1. Mine tables -> work/paper.txt, work/tables/*.csv, work/tables.json
python3 $S/table_mine.py --pdf /input/<paper>.pdf
#    Any status:"manual" table: open its worksheet.md, transcribe VERBATIM
#    into the promised csv_path, flip the entry to "mined" in tables.json.
# 2. Harvest figure crops -> work/figures/*.png, work/figures.json
python3 $S/figure_harvest.py --pdf /input/<paper>.pdf
#    LOOK at each crop; wrong zone -> re-run with --override fig-N=x0,y0,x1,y1
# 3. Replot replot-candidates from CSVs (skip if exit 3; note exception)
python3 $S/replot.py --spec /app/work/replot_spec.json
# 4. Write /app/work/plan.json (slides with refs), then audit — fix plan on FAIL
python3 $S/number_audit.py --plan /app/work/plan.json --paper-text /app/work/paper.txt \
    --tables /app/work/tables.json --figures /app/work/figures.json \
    --out /app/output/number_audit.json
# 5. Build the deck (refuses on audit FAIL), then finalize result.json
python3 $S/build_deck.py --plan /app/work/plan.json \
    --audit /app/output/number_audit.json --template /input/target-template.pptx
python3 $S/result_make.py --case /input/case.json --out /app/output/result.json \
    --status success --set-json 'compliance_checks={"number_audit":"PASS"}'
```

## Exception table

| Situation | Handling |
|---|---|
| Table block resists parsing | `table-N.worksheet.md` written (raw block + schema, marked manual-transcribe); agent transcribes **verbatim** into `table-N.csv`, flips `tables.json` status to `mined`; audit re-checks the numbers |
| `matplotlib` missing | `replot.py` exits 3; deliver native tables + crops only; add `replot-unavailable` to `exceptions`; status may stay `success` with the limit stated, or `partial` if charts were required |
| Figure crop zone wrong | Re-run `figure_harvest.py --override fig-N=x0,y0,x1,y1` (PDF pts, top-left origin); re-inspect the rendered PNG |
| Figure caption missing | Use a section-text locator: find the in-text reference ("see Figure 3") to bound the zone manually via `--override`; note it in `exceptions` |
| Audit FAIL | Fix `plan.json` (remove/rebind the offending number or ref), re-audit. Never patch the checker, never fabricate a source |
| `pdftotext`/`pdftoppm` missing | Cannot mine/harvest: `unable_to_determine` or `partial` with the exact missing capability in `exceptions` |
| `soffice` missing | Skip `presentation.pdf` + previews; note in `exceptions` (pptx is the primary deliverable) |
| Template theme | Only `sldSz` is adopted; full theme inheritance is out of scope — declare it in `exceptions` |

## Scripts

| Script | Role |
|---|---|
| `scripts/table_mine.py` | `pdftotext -layout` → caption `^Table\s*\d+` → parse following aligned block by column gaps → `table-N.csv` (verbatim cells) or manual worksheet → `tables.json` |
| `scripts/figure_harvest.py` | `pdftotext -bbox-layout` → caption zones → `pdftoppm` crops → `figures.json`; deterministic `bitmap-embed` vs `replot-candidate` classification |
| `scripts/replot.py` | spec-driven verbatim replot via matplotlib (optional); in-chart source footnote; `*.provenance.json` keeps the raw CSV strings |
| `scripts/number_audit.py` | fail-closed check of numbers / refs / units for the slide plan; exit 1 on FAIL |
| `scripts/build_deck.py` | pure-stdlib pptx writer: native `<a:tbl>` tables, chart/figure slides with provenance footers, speaker notes; refuses on audit FAIL; optional soffice PDF + previews |
| `scripts/result_make.py` | early-partial + final `result.json` honoring the case's `output_contract` |

Policy details (classification rule, verbatim rules, unit rules) are in
[references/rebind_policy.md](references/rebind_policy.md).

## Synthetic example

`examples/` contains a fully synthetic end-to-end run (fictional "SynNet"
paper, invented numbers): `bash examples/run_example.sh` builds the deck and
finishes with a **negative demo** — a plan containing a hallucinated `97.1%`
that the audit must reject. The synthetic deck title starts with
`SYNTHETIC EXAMPLE —`, chart footnotes carry `(synthetic demo)`, and
`result.json` carries `"synthetic_example": true`. Synthetic outputs must keep
these markers; they are not real research results.
