# Gate criteria — exact machine-checked checklists

`gate.py <stage>` runs the checks below, writes `work/gate-<stage>.json`
(`{stage, checks: [{name, ok, detail}], verdict: PASS|FAIL, ts}`), appends a
`gate` entry to the journal, and exits 1 on FAIL. A gate is PASS only if every
check is ok. Gates are never skipped: fix, then re-run the same gate.

## Stage: plan

| # | check name | ok iff |
|---|---|---|
| 1 | `plan-exists` | `work/plan.json` exists |
| 2 | `plan-parses` | file parses as JSON |
| 3 | `plan-has-slides` | `plan.slides` is a list with ≥ 1 slide |
| 4 | `slide-count-within-limit` | slide count ≤ limit, where limit = `max_slides`/`slide_limit`/`limit`/`maxSlides` from `/input/artifacts/slide-workorder.json` when present, else 20 |
| 5 | `every-slide-has-title` | every slide has a non-empty `title` |
| 6 | `claimed-evidence-nonempty` | every slide that has an `evidence` key has a non-empty list |
| 7 | `evidence-quotes-nonempty` | every evidence item has a non-empty quote (string item itself, or `item["quote"]`) |

## Stage: build

| # | check name | ok iff |
|---|---|---|
| 1 | `pptx-exists` | `/app/output/presentation.pptx` exists |
| 2 | `pptx-valid-zip` | opens as a zip (OOXML container) |
| 3 | `has-slide-xml` | ≥ 1 `ppt/slides/slideN.xml` part |
| 4 | `has-notes-xml` | ≥ 1 `ppt/notesSlides/notesSlideN.xml` part |
| 5 | `all-xml-well-formed` | every `.xml`/`.rels` part parses with a real XML parser (a deck PowerPoint cannot parse is not a deck) |
| 6 | `presentation-lists-slides` | `ppt/presentation.xml` `sldIdLst` entry count == slide part count |
| 7 | `slide-count-matches-plan` | pptx slide count == `len(plan.slides)` from `work/plan.json` |
| 8 | `every-slide-has-text` | every slide XML contains ≥ 1 non-empty `<a:t>` run |
| 9 | `no-placeholder-text` | no literal `TODO` or `Lorem` (case-insensitive) in any slide XML |

## Stage: render

Renderer detected via `shutil.which("soffice")`.

If `soffice` is **absent**: a single check `renderer-absent` with `ok: true`
whose detail states that PDF export and previews were not produced. This is an
honest degradation, not a hidden failure — the delivery manifest, RUN_REPORT
and result.json exceptions all repeat it.

If `soffice` is **present**:

| # | check name | ok iff |
|---|---|---|
| 1 | `pdf-exists` | `/app/output/presentation.pdf` exists |
| 2 | `pdf-page-count-matches` | PDF page count == pptx slide count (via `pdfinfo`, else form-feed count from `pdftotext`) |
| 3 | `preview-pngs-exist` | ≥ 1 PNG under `/app/output/previews/` |
