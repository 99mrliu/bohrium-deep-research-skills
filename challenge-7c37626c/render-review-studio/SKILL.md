---
name: render-review-studio
description: Make every formula-analysis deliverable visually inspectable — strict mathtext rendering of transcriptions to PNG, side-by-side comparison sheets against the source page, variable-table rendering, and a review pack that fails closed when a promised visual artifact is missing; use whenever a task's value depends on a human reviewer being able to see that the rendered structure matches the source.
---

# render-review-studio: downstream rendering engineering (下游渲染工程)

Core stance: **a transcription no human can see is not verified.** This
skill's center of gravity is downstream rendering: whatever the reading
pipeline produces — LaTeX transcriptions, variable tables, derivation
summaries — is rendered into real PNG/PDF previews under `/app/output`,
placed side by side with the source evidence, and assembled into a review
pack whose completeness is enforced. The skill does not decide what the
formula means; it makes the result inspectable and refuses to call the pack
complete when an image is missing or blank.

## Runtime contract

- Input: `/input/case.json` and `task.md`; materials under
  `case.json.artifacts` (publisher XML, formula subsets, PDF). Read the
  actual files.
- Create `/app/work` immediately; write `/app/output/result.json` early as an
  honest partial with the original `case_id` and every `output_contract`
  field; improve incrementally.
- Rendered artifacts are **runtime artifacts** (binary PNG/PDF allowed) and
  are listed in `result.json.artifacts` with byte sizes so a reviewer can
  open them. `result.json` uses the contract's own field names, types and
  status enumeration; a `partial` result names exactly which artifact could
  not be produced.
- Never present prepared answers: the PNGs are rendered in-run from the
  actual transcriptions and the actual source pages.

## Workflow

1. **Bootstrap.** `python3 scripts/case_bootstrap.py --input /input --work /app/work --out /app/output`.
2. **Produce transcriptions** (the agent's own reading, or another skill's
   verified inventory) and write `/app/work/formulas.json`:
   `{"formulas": [{"id": "eq1", "latex": "D = \\frac{\\mu k_{\\mathrm{B}} T}{q}", "source": "publisher-source.xml#eq1"}]}`.
   Write `/app/work/variables.json` for the symbol table
   (`{"rows": [{"symbol": "D", "definition": "...", "unit": "...", "source": "..."}]}`).
3. **Render.** `python3 scripts/render_formula.py --work /app/work --out /app/output/render`
   renders every formula with matplotlib mathtext in strict mode: a LaTeX
   construct mathtext cannot typeset is reported as `unrenderable` with the
   engine's error, never silently dropped or "approximately" drawn.
4. **Compare.** `python3 scripts/compare_sheet.py --case /input/case.json --input /input --work /app/work --out /app/output/render`
   rasterizes the source PDF page (via `pdftoppm`, when a PDF artifact
   exists) and composes `[source evidence | rendered transcription]` sheets
   per formula. Without a PDF, the sheet pairs the rendered transcription
   with the formula's `source` reference and says so.
5. **Table.** `python3 scripts/table_render.py --work /app/work --out /app/output/render`
   renders the variable table to a paginated PNG.
6. **Pack and enforce.** `python3 scripts/review_pack.py --work /app/work --out /app/output`
   writes `/app/output/review_report.md` linking every preview, verifies
   each promised PNG exists and is non-trivial (byte-size floor), and folds
   the artifact manifest into `result.json`. A missing or zero-byte preview
   degrades the status to `partial` with the artifact named.

## Exception handling

- `matplotlib` unavailable: report `renderer_unavailable` for every render
  target, keep the LaTeX/JSON deliverables, status `partial`. Never claim a
  preview that was not produced.
- `pdftoppm` unavailable or PDF unreadable: comparison sheets degrade to
  transcription-only panels with the reason printed on the sheet.
- Mathtext engine error: the formula is listed `unrenderable` with the error
  message; the fix belongs upstream (simplify the LaTeX), not in faking an
  image.
- Missing-formula branch: there is nothing to render — the pack says so and
  the status is `insufficient_evidence` for visual deliverables.

## Minimal example (SYNTHETIC — not a platform case, not evidence)

`examples/run_synthetic_example.sh` renders two fabricated formulas, builds
a side-by-side sheet against a small synthetic source page, renders a
three-row variable table, and packs the previews; one formula is
deliberately malformed to demonstrate the `unrenderable` path. All materials
are synthetic.

## Requirements and limitations

Python 3.9+; matplotlib required for rendering (declared dependency);
`pdftoppm` optional. Mathtext is not full LaTeX — macros, tables and
specialized packages are unsupported and will be reported as `unrenderable`.
The visual check proves the *rendering* is faithful to the transcription; the
*transcription's* fidelity to the source is the upstream skill's
responsibility (or the agent's own reading).
