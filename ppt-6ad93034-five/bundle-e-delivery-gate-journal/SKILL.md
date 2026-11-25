---
name: delivery-gate-journal
description: Stage gates with machine-checked exit criteria, an append-only hash-chained run journal, a result.json watchdog that keeps an honest partial result at every kill point, and a replay-verifiable sha256 delivery manifest — process quality control / delivery governance for academic PPT production runs (学术 PPT 生成与编辑). Turns "it ran once" into "anyone can audit and replay the run". Boundary: the bundled builder (mini_build.py) is deliberately minimal; the gates/journal/watchdog can wrap any PPT builder.
---

# delivery-gate-journal — governed academic deck production

## Philosophy

Trust in a produced deck comes from three mechanisms, not from confidence:

1. **Gates you cannot pass without evidence.** plan → build → render each have
   machine-checked exit criteria (`gate.py`). A failed gate stops the pipeline;
   you fix the cause and re-run the gate. Gates are never skipped.
2. **A journal you cannot edit without detection.** Every meaningful action is
   appended to `journal.jsonl`, each entry hash-chained to the previous one and
   pinning the sha256 of its input/output files. Rewriting history breaks the chain.
3. **A result that is honest at every interruption.** `watchdog.py` writes a valid
   `result.json` *before any real work* and updates it after every stage, so a kill
   or timeout at any point leaves a correct `partial` result. `success` can only be
   written after all three gates PASS.

## Runtime contract

- The skill is installed at `/skills/weekly-skill`. Scripts run as
  `python3 /skills/weekly-skill/scripts/<name>.py`. **Pure stdlib only. No network.**
- Original inputs (read REAL files, never assume): `/input/case.json`, `/input/task.md`,
  the paper PDF, usually `/input/target-template.pptx`, optionally
  `/input/starting-deck.pptx` and `/input/artifacts/slide-workorder.json`.
- Work under `/app/work`; deliverables under `/app/output`:
  `presentation.pptx`, `presentation.pdf` + `previews/` when `soffice` exists,
  `RUN_REPORT.md`, `delivery_manifest.json` (sha256 of every artifact),
  a `journal.jsonl` copy, gate reports, and `result.json`.
- Directories are configurable via env vars `CASE_INPUT_DIR`, `CASE_WORK_DIR`,
  `CASE_OUTPUT_DIR` (defaults `/input`, `/app/work`, `/app/output`).
- `pdftotext` / `pdftoppm` / `soffice` / `pdfinfo` are detected via `shutil.which`;
  absence degrades gracefully and is **recorded** (journal tool table, render gate
  `renderer-absent`, manifest, honest notes) — never hidden.
- `result.json` MUST contain the original `case_id` (`case.json` key `case_id` or `id`)
  and EVERY root field of the case's `output_contract` (read from `case.json`; if absent
  use defaults: `status`, `editable_source`, `export_artifact`, `content_map`,
  `compliance_checks`, `exceptions`). `status ∈ success | partial |
  unable_to_determine | refused`; `partial` states limits precisely in `exceptions`.
  A `synthetic_example` flag in `case.json` is passed through. **Never fabricate.**

## Workflow (run in order; exact commands)

1. **Bootstrap honesty FIRST** — before touching the paper:
   ```
   python3 /skills/weekly-skill/scripts/watchdog.py init --case /input/case.json
   python3 /skills/weekly-skill/scripts/journal.py init
   ```
   `result.json` (status `partial`) and journal entry 0 (input hashes + tool versions) now exist.
2. **Ground and plan** — extract text, then write `/app/work/plan.json`
   (`{"meta": {...}, "slides": [{"title", "bullets", "notes", "evidence": [{"quote", "source"}]}]}`),
   every factual claim carrying a verbatim quote from `paper.txt`; then gate it:
   ```
   python3 /skills/weekly-skill/scripts/pdf_text.py
   python3 /skills/weekly-skill/scripts/journal.py log --kind command --cmd "plan written" \
     --inputs work/paper.txt --outputs work/plan.json --note "plan grounded in paper text"
   python3 /skills/weekly-skill/scripts/gate.py plan
   ```
3. **Build** the deck (bundled minimal builder, or any other builder — the gate checks the output, not the tool):
   ```
   python3 /skills/weekly-skill/scripts/mini_build.py
   python3 /skills/weekly-skill/scripts/journal.py log --kind command --cmd "mini_build.py" \
     --inputs work/plan.json --outputs app-output/presentation.pptx
   python3 /skills/weekly-skill/scripts/gate.py build
   ```
4. **Render/export** — if `soffice` exists convert to PDF and rasterize previews with
   `pdftoppm`; journal the export; then gate:
   ```
   python3 /skills/weekly-skill/scripts/gate.py render
   ```
   If `soffice` is absent the render gate records `renderer-absent` (ok:true) and the
   manifest/result say so plainly.
5. **Package the delivery** — after each stage above, advance the watchdog
   (`watchdog.py advance --stage <name> [--set-json 'k=<json>']... [--exception "..."]...`;
   it refuses to record artifact paths that do not exist). Then:
   ```
   python3 /skills/weekly-skill/scripts/replay.py          # delivery_manifest.json + RUN_REPORT.md
   python3 /skills/weekly-skill/scripts/replay.py --check  # re-verify chain + artifact hashes
   python3 /skills/weekly-skill/scripts/journal.py verify
   cp /app/work/journal.jsonl /app/output/journal.jsonl    # ship the journal with the deck
   ```
6. **Finalize**:
   ```
   python3 /skills/weekly-skill/scripts/watchdog.py finalize --status success
   ```
   Refused unless all three gates PASS; otherwise finalize as `partial` with precise exceptions.

## Exception table

| Situation | Required behavior |
|---|---|
| Any gate FAILs | **Stop.** Fix the underlying artifact, re-run the same gate. Never skip a gate, never hand-edit a gate report. |
| `soffice` absent | Render gate records `renderer-absent` (ok:true); manifest + result.json + RUN_REPORT state that PDF/previews were not produced. |
| Kill / timeout at any point | `result.json` already exists as a valid honest `partial` (written before real work, updated after every stage). Nothing to do. |
| `journal.py verify` reports tampered | Investigate; do NOT delete or rewrite the journal. Finalize `partial` with an exception describing the tamper. |
| Input missing/unreadable (e.g. no PDF, no case.json) | `watchdog.py advance --exception "..."`, finalize `partial` (or `unable_to_determine`); never invent content. |
| Plan evidence cannot be grounded in paper text | Do not fabricate quotes; mark the slide's limits in `exceptions`. |

## Scripts (all pure stdlib)

| Script | Role |
|---|---|
| `scripts/watchdog.py` | Owns `result.json`: `init` / `advance` / `finalize`. See `references/journal_format.md` for the result contract. |
| `scripts/journal.py` | Append-only hash-chained journal: `init` / `log` / `verify`. |
| `scripts/gate.py` | Stage gates `plan` / `build` / `render`; exact checklists in `references/gate_criteria.md`. |
| `scripts/mini_build.py` | Deliberately minimal plan→pptx builder (title + bullets + notes + footer source line). Replaceable — gates wrap any builder. |
| `scripts/pdf_text.py` | Tiny pdftotext wrapper (stdlib fallback) producing `work/paper.txt`. |
| `scripts/replay.py` | Writes `delivery_manifest.json` + `RUN_REPORT.md`; `--check` re-verifies everything. |

## Synthetic example

`examples/` contains a fully synthetic, self-running demo (fixture paper marked
SYNTHETIC, synthetic case `synthetic-demo-005`, plus a deliberate tamper-detection
negative demo). Run `bash examples/run_example.sh`. Its outputs are demo artifacts
labeled 合成示例/synthetic, not real research products.
