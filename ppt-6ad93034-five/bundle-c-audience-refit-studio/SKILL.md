---
name: audience-refit-studio
description: Surgical audience/language/length refit of existing academic decks (switch audience advisor/reviewer/peer, switch language zh<->en, compress or expand slide count) with a locked terminology table, numeric-conservation auditing, and pptx XML surgery that touches only the slides a work order names. Built for 学术 PPT 生成与编辑 edit/adapt tasks. Boundary: this is NOT a from-scratch deck builder — if no starting deck exists in edit/adapt mode, say so and produce a plan-only partial result.
---

# audience-refit-studio

## Philosophy: editing is surgery with a consent form

An existing deck is a patient's body. **Nothing changes without an op and a
reason** — every edit is an entry in `refit_ops.json` carrying a non-empty
`reason`, and every applied op lands in `change_record.json`. **Facts are
conserved quantities**: numbers and locked terminology may move between
slides, but they may never appear, disappear, or mutate silently. If the
audit fails, **fix the ops, not the checker** — the checker has no opinion
about style, only about conservation and scope.

The skill never auto-paraphrases scientific content. The agent writes the
actual new slide text; the scripts enforce the policy around it.

## Runtime contract

- The skill is installed at `/skills/weekly-skill`. Scripts run as
  `python3 /skills/weekly-skill/scripts/<name>.py`.
- Inputs live under `/input`: `case.json`, `task.md`, the paper PDF,
  usually `target-template.pptx`, optionally `starting-deck.pptx`
  (**required** in edit/adapt mode) and `artifacts/slide-workorder.json`.
  Read the REAL files; never invent inputs.
- Work under `/app/work`; deliver under `/app/output`:
  `presentation.pptx` (edited, editable), `presentation.pdf` + preview
  images when `soffice` is available (detect via `shutil.which`; degrade
  gracefully), copies of `refit_audit.json` + `terms.json`, and
  `result.json`.
- Flags and/or env vars `CASE_INPUT_DIR`, `CASE_WORK_DIR`,
  `CASE_OUTPUT_DIR` (defaults `/input`, `/app/work`, `/app/output`).
- Pure stdlib only (pptx handled with `zipfile` + `xml.etree`; namespaces
  registered to avoid `ns0:` prefixes). No network. `pdftotext`/`soffice`
  detected via `shutil.which`; if absent, work from any supplied plain-text
  extraction and note the exception.
- `result.json` MUST contain the original `case_id` (key `case_id` or `id`
  from `case.json`) and EVERY root field of the case's `output_contract`
  (if absent, defaults: `status`, `editable_source`, `export_artifact`,
  `content_map`, `compliance_checks`, `exceptions`).
  `status ∈ success | partial | unable_to_determine | refused`; a `partial`
  status states its limits precisely in `exceptions`. **Secure a partial
  `result.json` EARLY** (run `result_make.py --status partial` right after
  reading the case). Never fabricate numbers or terms.

## Workflow (6 steps)

1. **Read the case and the deck.** Parse `case.json`, `task.md`, the
   work order (`/input/artifacts/slide-workorder.json` or equivalent). In
   edit/adapt mode, refuse politely if `starting-deck.pptx` is missing
   (plan-only partial). Convert the paper PDF to text
   (`pdftotext -layout` if present) into `/app/work/paper.txt`.
   Immediately write a partial `result.json`.
2. **Extract the locked terminology table.**
   `term_table.py --paper-text work/paper.txt [--deck-model work/model.json]`
   after `deck_io.py read --deck ... --out work/model.json`. Locked terms
   must survive any refit byte-identically.
3. **Generate the editing brief.**
   `audience_brief.py --workorder ... --terms work/terms.json --out work/refit_brief.md`.
   This fixes audience voice, language-switch rules, and compression order.
4. **Write `refit_ops.json` by hand** following the brief: the actual new
   slide text, one op per change, every op with a reason, honest
   `introduced_numbers` / `dropped_numbers` / `dropped_terms` declarations.
5. **Apply.** `refit_apply.py --model work/model.json --ops work/refit_ops.json
   --src <starting-deck.pptx> --out /app/output/presentation.pptx`.
6. **Audit and report.** `conserve_check.py ... --out /app/output/refit_audit.json`
   (exit 1 on any FAIL — fix the ops and re-apply), copy `terms.json`,
   export PDF/previews if `soffice` exists, then finalize with
   `result_make.py --status success`.

## Exception table

| situation | action |
|---|---|
| No `starting-deck.pptx` in edit/adapt mode | Politely refuse the edit; produce a plan-only `partial` result (brief + proposed ops, no pptx). Status `partial` with a precise exception. |
| An op fails the audit | Fix `refit_ops.json` and re-apply. Never weaken or skip `conserve_check.py`. |
| Language switch requested but no `terms.json` | Run `term_table.py` FIRST. Never translate locked surfaces; add a first-use gloss in the target language. |
| Target slide count unreachable | Land at the nearest feasible count and record an exact exception in `result.json` ("merged X+Y; count 5→4, target 3 unreachable without dropping evidence slide 4"). |
| `soffice`/`pdftotext` missing | Degrade gracefully: skip PDF export / use supplied text; note the exception. |
| Paper text unavailable | `unable_to_determine` for numeric/term checks; state the limit precisely. |

## Scripts

| script | role |
|---|---|
| `scripts/deck_io.py` | pptx ⇄ JSON model (`read`/`write`). XML surgery; per-slide text sha256 baselines; delete/reorder slides via `sldIdLst` + `[Content_Types].xml` + rels; `add_slide` clones a donor part. |
| `scripts/term_table.py` | Locked terminology extraction (abbreviations both directions, hyphenated compounds, math symbols, proposed methods) → `work/terms.json`. |
| `scripts/audience_brief.py` | Deterministic editing brief (audience profile, language rules, compression plan). |
| `scripts/refit_apply.py` | Applies `refit_ops.json` (ops require reasons) → new pptx + `change_record.json`. |
| `scripts/conserve_check.py` | Numeric-conservation, terminology, surgical-scope and slide-count audit → `refit_audit.json`; exit 1 on FAIL. |
| `scripts/result_make.py` | Merge-safe `result.json` builder honouring the case output contract. |

## Op vocabulary (see `references/refit_policies.md` for the full policy)

`rewrite_paras`, `set_notes`, `delete_slide`, `move_slide`, `add_slide`.
Indices are 0-based positions in the **current** deck state at the moment
the op is applied; ops apply in list order. Text styling is preserved by
putting full new text in the first run and blanking the rest — runs are
never rebuilt from scratch.

## Synthetic example

`examples/run_example.sh` runs the whole pipeline end-to-end on an
invented "SynGraph" deck (every slide marked `SYNTHETIC EXAMPLE —`),
including a **negative demo**: `refit_ops_bad.json` fabricates "97.1%" and
`conserve_check.py` must exit 1 naming that number. See
`examples/expected_output.md` for what each artifact proves.
