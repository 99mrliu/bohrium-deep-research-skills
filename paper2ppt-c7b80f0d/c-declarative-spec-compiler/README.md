# ppt-spec-compiler

Compile an academic paper into an editable, evidence-traceable `.pptx` deck.
The human/agent hand-writes **one** declarative artifact — `deck.spec.json`
(one claim per slide, bullets, evidence locators, figure image paths, speaker
notes) — and a deterministic, zero-dependency compiler performs **all**
mechanical work: validation, layout, bullet caps, overflow-to-backup, text-fit
with a readability floor, evidence footers, aspect-preserving images, notes
slides, template inheritance, and a full audit trail in `compile_report.json`.

Designed for the Bohrium Playground challenge `ppt-c7b80f0d` (论文转学术 PPT),
reusable for any paper→slides task.

## Install

No installation: the skill is a directory of UTF-8 text files. The evaluator
installs it at `/skills/weekly-skill`; entry point is `SKILL.md`. Elsewhere,
copy the directory and call the scripts by path.

## Dependencies and versions

| Component | Requirement |
|---|---|
| Python | 3.8+ stdlib only for all scripts |
| `python-pptx` | optional; only imported inside `try/except`. Enables the **template backend** (tested with 1.0.2). Without it the compiler automatically uses the **builtin** pure-stdlib OOXML backend and discloses the deviation |
| `pdftotext`, `pdftoppm` | poppler-utils; paper text extraction, page renders, figure cropping, preview PNGs |
| `soffice` | optional office renderer for PDF/PNG preview; absence is handled gracefully (`renderer_unavailable`, exit 0) |
| `fc-list` | optional; font summary in `render_manifest.json` |

## Spec language quick reference

`deck.spec.json` = `{ "meta": {...}, "slides": [...] }` (full draft-07 schema:
`spec_schema.json`; enforced by `scripts/validate_spec.py`).

- `meta`: `case_id`, `title` (required), `audience`, `language`,
  `slide_limit` (default 20), `max_bullets` (default 6), `footer_prefix`
  (default `"Source: "`), `time_limit`.
- slide: `id`, `kind` ∈ {title, section, content, figure, table, two-column,
  conclusion, backup}, `claim` (exactly one sentence; required on
  content/figure/table/two-column/conclusion), `title`, `bullets[]`,
  `evidence[]` = `{ref, page?, quote?}` (required on content/figure/table),
  `image` = `{path, caption?}`, `table` = `{columns, rows}`, `notes`
  (required everywhere; must not repeat bullets).

Compile-time enforcement (all recorded in `compile_report.json`): slide-limit
overflow → labelled backup section; bullets over cap → demoted to notes
(`[DEMOTED:bullet-cap]`); long titles wrapped/elided; estimated text overflow →
font ladder 20→18→16→14→12 pt with a 12 pt floor, then demotion
(`[DEMOTED:text-fit]`); tables > 8 rows compacted to notes; aspect-preserved
image placement; per-slide evidence footer; real notes slides.

## Commands

```bash
python3 scripts/validate_spec.py  --spec deck.spec.json
python3 scripts/compile_deck.py   --spec deck.spec.json --out deck.pptx \
    [--template T.pptx | --start-deck S.pptx] --report compile_report.json
python3 scripts/render_preview.py --deck deck.pptx --outdir preview \
    --manifest render_manifest.json
python3 scripts/make_result.py    --case /input/case.json \
    --out /app/output/result.json --status complete
```

Exit codes: validator 0/1/2; compiler 0/1/2 (report is still written on
failure); render_preview 0 (incl. graceful `renderer_unavailable`) / 1;
make_result 0.

## Repository layout

```
SKILL.md                  agent-facing instructions (start here)
spec_schema.json          draft-07 schema of deck.spec.json
scripts/validate_spec.py  stdlib schema validator (itemized errors)
scripts/compile_deck.py   spec -> .pptx compiler (template + builtin backends)
scripts/render_preview.py soffice -> PDF -> pdftoppm PNGs + manifest
scripts/make_result.py    result.json builder honoring output_contract
references/spec_authoring.md  paper -> spec distillation guide
references/text_fit.md    fitting/demotion policy and constants
examples/minimal_example.md   end-to-end walkthrough (marked EXAMPLE)
```

## Limitations

- Builtin backend renders tables as aligned text lines, not real OOXML tables
  (the template backend creates real table shapes). 
- The text-fit estimator is a deterministic heuristic (documented constants),
  not a glyph-accurate layout engine; the PDF/PNG preview step is the ground
  truth and must be inspected.
- Images: PNG only in the builtin backend (header-parsed); convert others with
  pdftoppm/matplotlib first. The template backend accepts what python-pptx accepts.
- `--start-deck` rewrites slides in order and drops non-placeholder shapes on
  rewritten slides; complex per-slide decorations of a starting deck are not
  preserved.
- The skill does not judge scientific correctness of the paper; evidence
  locators trace to what the paper actually says, and spec content must be
  copied verbatim.

## Maintenance

- Version: 1.0.0 (compiler version stamped into `compile_report.json`).
- Scripts are stdlib-only; keep it that way (python-pptx stays optional).
- If the schema changes, update `spec_schema.json`, `validate_spec.py`,
  `references/spec_authoring.md` and this README together.
- Test after changes: py_compile all scripts, run the smoke flow in
  `examples/minimal_example.md`, open the output with python-pptx and with an
  office renderer.
- Issues/improvements: see the GitHub URL in `GITHUB_URL.txt`.
