---
name: ppt-safe-harbor-delivery
description: Budget-aware paper→academic-PPT execution protocol that guarantees a valid deliverable set at every moment — scaffold an honestly-partial output first, upgrade slide-by-slide under explicit time/request checkpoints, and finish with a mandatory render-verify pass. Trigger when asked to convert a paper (PDF) into a slide deck (.pptx) inside a time- or request-limited harness, especially with an organizer template, slide/time limits, or an output_contract to satisfy.
---

# PPT Safe-Harbor Delivery

You convert a paper into an academic slide deck **under a hard budget** (default: 64 model
requests, 900 s, 16384 tokens/response). The failure mode this skill prevents: getting cut
off mid-build and delivering nothing valid, or delivering a deck never render-verified.

**Core rule (checkpoint invariant): after EVERY action, `/app/output` contains a complete,
valid deliverable set.** You achieve this by building the full valid set FIRST (partial but
honest), then upgrading it one slide at a time. Never hold the only copy of your work in
conversation context — write it to disk immediately.

## When to use

- Input is a paper (PDF) and the task asks for slides/PPT/deck, or
- `case.json` names slide/deck outputs in its `output_contract`, or
- an organizer `.pptx` template or starting deck is provided with audience/time/slide limits.

## Runtime contract

- Inputs: `/input/case.json`, `/input/task.md`. **Read the actual files**; never trust labels.
  `environment/resources.yaml` (if present) lists provided tools: pdf-text-tool (`pdftotext`),
  pdf-render-tool (`pdftoppm`), ocr-tool, latex-compiler, office-renderer (LibreOffice/`soffice`),
  browser-automation, font-discovery (`fc-list`), scientific-python. Verify each on PATH before
  relying on it.
- Work under `/app/work`; final artifacts under `/app/output`, including `/app/output/result.json`
  with the original `case_id` and **every field named by the case's `output_contract`** (the
  case's contract wins over any default).
- `result.json` carries honest `status` (`success` | `partial` | `unable_to_determine`),
  `sources`, `uncertainty` (list), and a change record. A partial result must name its limits.
- Editable slide outputs must also have real rendered PDF/PNG previews (via `render_preview.py`).
- Never fabricate paper content, figure numbers, metric values, software state, or scores.
  Unextracted content stays as an explicit `[pending: ...]` placeholder.

## The protocol: P0 → P4

Budget percentages refer to elapsed wall time vs. the total budget (default 900 s) and, in
parallel, model requests used vs. total (default 64). Full table with abort rules:
`references/budget_protocol.md`. How to fill `result.json`: `references/output_contract.md`.

### P0 — Scaffold (≤10% time / ≤6 requests) — DO THIS FIRST, before reading the paper deeply

Run, in order:

```bash
python3 /skills/weekly-skill/scripts/scaffold_output.py \
    --case /input/case.json --task /input/task.md \
    --outdir /app/output --workdir /app/work
python3 /skills/weekly-skill/scripts/build_skeleton_deck.py \
    --state /app/work/session_state.json --out /app/output/deck.pptx
# if the case gives a template AND paper text already exists:
#   add --template <path-from-case.json> --titles-from /app/work/paper.txt
python3 /skills/weekly-skill/scripts/validate_output.py \
    --outdir /app/output --case /input/case.json --state /app/work/session_state.json
```

After P0 you have: a valid partial `result.json` (case_id + all contract fields as honest
placeholders + uncertainty list), a skeleton `deck.pptx` covering every mandatory main-line
page type with `[pending: ...]` bullets and TODO speaker notes, a slide-by-slide plan in
`session_state.json`, and a validation report. **If the run died now, the submission is valid.**

### P1 — Extract & plan (≤35% time / ≤22 requests)

1. `pdftotext -layout <paper.pdf> /app/work/paper.txt` (see exception table for failures).
2. Extract: title/authors/venue; problem statement; gap/research question; method summary;
   per key figure/table: the verbatim metric values + their section/table anchor; limitations;
   conclusions. Save each as small files under `/app/work/extract/` (one per planned slide:
   `02-problem.bullets.txt`, `02-problem.notes.txt`, ...). Writing files, not notes in your
   head, is what makes mid-run interruption survivable.
3. Reconcile with `session_state.json` `slide_plan`: match evidence slides 1:1 to the paper's
   key figures/tables; if the slide limit forces fewer, keep the strongest results.

### P2 — Per-slide upgrades (≤80% time / ≤50 requests), main-line priority order

Strict order: **title → problem → gap/question → method → one evidence slide per key
figure/table → limitations → conclusions → backup.** Never start a lower-priority slide
while a higher one is still a placeholder. For each slide:

```bash
python3 /skills/weekly-skill/scripts/patch_slide.py --deck /app/output/deck.pptx \
    --slide N --title "..." --bullets-file /app/work/extract/NN-x.bullets.txt \
    --notes-file /app/work/extract/NN-x.notes.txt --footer "Source: §3.2, Table 1"
python3 /skills/weekly-skill/scripts/validate_output.py --outdir /app/output \
    --case /input/case.json --state /app/work/session_state.json
```

- Every bullet must be traceable to paper text; put the anchor (§/Fig./Table) in the footer.
- Numbers verbatim from the paper. If unsure of a value, write `[pending: verify §X]`, not a guess.
- One slide per request if possible; **each model request must end with a state update +
  validate run** so the invariant holds.
- **Checkpoint:** if >50% of time is used and the method slide is not done → compress the plan
  (re-run `scaffold_output.py` won't shrink it; edit `slide_plan` in `session_state.json` to ≤8
  slides and rebuild the skeleton) and jump any remaining low-priority slides to placeholder.
- **Checkpoint:** at 80% time OR 50 requests → stop adding content immediately, go to P3.

### P3 — Render & verify (≤95% time; reserve the last ~120 s for this + P4)

```bash
python3 /skills/weekly-skill/scripts/render_preview.py \
    --deck /app/output/deck.pptx --outdir /app/output/preview
python3 /skills/weekly-skill/scripts/validate_output.py \
    --outdir /app/output --case /input/case.json --state /app/work/session_state.json
```

`render_preview.py` produces `deck.pdf` + per-slide PNGs (150 dpi) and a
`render_manifest.json` recording tool paths/versions and the font summary. If it reports
`renderer_unavailable`, do NOT claim render verification — disclose it in `uncertainty`.
If PNGs reveal a broken slide (overflow, wrong text), patch that slide and re-render only if
time permits; otherwise document the defect in `uncertainty` and keep the last valid deck.

### P4 — Finalize `result.json` (last ~120 s)

Update `/app/output/result.json` (edit the file directly or via a heredoc): set final
`status` (`success` only if every contract field is filled with real content AND render
verified; else `partial` with named limits), fill every contract field from the real
artifacts (e.g. deck path, slide count, summaries actually on the slides), shrink
`uncertainty` to what is genuinely unresolved, append the change record (see
`references/output_contract.md`), copy sources actually used. Final `validate_output.py`
run must print `deliverable_state: complete` or `partial` — never `broken`.

## Slide priority order (drop from the bottom when limits bite)

1. title 2. problem 3. gap/question 4. method 5. evidence slides (one per key figure/table,
strongest first) 6. limitations 7. conclusions 8. backup. Title, method and conclusions
survive even a 3-slide limit.

## Template handling

- If the case provides an organizer `.pptx`: pass `--template` to `build_skeleton_deck.py`.
  With python-pptx importable, the builder deletes the template's slides and adds one slide
  per planned page using the template's own layouts, so masters/theme are inherited. Slide
  content is then patched **with python-pptx directly** — `patch_slide.py` will refuse and
  print the exact recipe (exit 3).
- If python-pptx is not importable, the builder falls back to the bundled stdlib writer,
  records the deviation in `session_state.json` — you must also record it in `result.json`
  (`uncertainty` + change record): organizer template not honored.
- A provided *starting deck* to adapt is a content source, not a template: extract its text
  (python-pptx if available, else unzip and grep slide XML), then build the skeleton as above.

## Exception table

| Situation | Action |
|---|---|
| Encrypted PDF (`pdftotext` fails "password") | Try empty password: `pdftotext -upw "" …`; else render pages with `pdftoppm` + OCR tool; else status `unable_to_determine` with the reason. |
| Image-only PDF (no text layer) | `pdftoppm -png -r 200` → OCR tool per page; if no OCR, extract only what PDF metadata/outlines give and mark all content placeholders pending; status ≤ `partial`. |
| python-pptx missing | Stdlib backend everywhere; patch via `patch_slide.py`; disclose if a template was ignored. |
| No `soffice` | `render_preview.py` writes manifest `renderer_unavailable`, exit 0; disclose; `validate_output.py` is the fallback integrity check; status ≤ `partial` for the render criterion. |
| Font substitution | Check `fc-list`; render manifest records available fonts; note substitutions in `uncertainty` only if they change layout materially. |
| Slide-limit overflow | Shrink `slide_plan` per priority order (drop backup → limitations → extra evidence first), rebuild skeleton, re-validate. |
| Starting-deck adaptation | Treat old deck as extract source only; never ship unverified legacy claims. |
| `case.json` missing/corrupt | Scaffold anyway with `case_id: "unknown-case"` and empty contract; note in `uncertainty`. |

## Delivery checklist (run mentally at P4)

- [ ] `result.json`: case_id matches case; every `output_contract` field present and non-placeholder; status honest; `uncertainty` names real limits; change record appended; sources listed.
- [ ] `deck.pptx`: opens (validation passes); slide count ≤ limit; no fabricated numbers; every content slide footer carries its §/Fig./Table anchor; speaker notes non-TODO on all main-line slides.
- [ ] `preview/` PNGs + `deck.pdf` exist, or `render_manifest.json` says `renderer_unavailable` and that is disclosed in `uncertainty`.
- [ ] `validation_report.json` exists; `deliverable_state` is `complete` or `partial`.
- [ ] Template honored, or deviation disclosed.

## Example

`examples/minimal_example.md` shows an end-to-end invocation sequence with示意 outputs.
It is an **illustration, not an official case result**.
