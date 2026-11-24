---
name: deliverable-forge
description: Turn a drafted introduction or related-work section into the real deliverables the case demands — enforced word budgets, a genuine editable .docx (true OOXML, not a renamed Markdown file), an inspectable PDF/text preview, and sentence-level change records for revisions. Use for rendering editable artifacts, enforcing length limits, producing previews, and recording manuscript edits.
---

# Deliverable Forge

The science of an introduction is judged on prose, but the score is collected
on **artifacts**: the right editable format, within the stated word limits,
with previews an evaluator can open, and with a change trail when the task is
a revision. This skill owns that downstream half of the job. Its center of
gravity is rendering and delivery engineering — it assumes the content is
already grounded and concentrates on producing artifacts that survive
inspection.

## When to use

- A draft exists and must be delivered as an editable artifact (docx or
  Markdown, as the case requires) plus `result.json`.
- The case imposes word limits per section or in total and they must be
  enforced, not estimated.
- The task is a revision: a change record with rationales must accompany the
  new version.
- A rendered preview (PDF when a renderer exists) is required for inspection.

Do not use this skill to judge scientific content — it checks budgets,
formats and traces, not whether claims are true. Pair it with source-grounding
work upstream.

## Runtime contract

1. Input is `/input/case.json` and `/input/task.md` plus declared materials.
   Read the actual files. Do not read withheld comparators.
2. Intermediate work under `/app/work`; final artifacts under `/app/output`.
3. `/app/output/result.json` carries `case_id` copied verbatim and **every
   field of the case's own `output_contract`** with the described nesting and
   types: the artifact object must name the real path, real format, the
   sections present and measured word counts; `version_and_boundary.changes`
   comes from the change record; `verification` aggregates the budget and
   rendering reports; `status` is honest — `partial` when an artifact is
   missing or a check failed, with the exact limit stated; `blocked` when no
   draft exists at all.
4. **Editable means editable.** A Markdown file is not a docx. When the case
   requires docx, produce a real OOXML package with `md2docx.py`; when it
   requires LaTeX or another native format, use the available compiler/tools
   and verify the output opens. Empty placeholder keys are not completion.
5. Save partial artifacts early: a within-budget draft plus a draft result.json
   in the first two thirds of the budget; render and verify in the last third.
   Scripts are cheap; do not re-render unchanged drafts.

## Method

### Step 1 — Enforce the word budget (before any rendering)

```sh
python3 <skill-dir>/scripts/word_budget.py --case /input/case.json \
  --draft /app/work/draft.md --out /app/work/word_report.json
```

Counts words per rhetorical part (background / related_work / gap /
contributions; heading-based when headings exist, cue-based otherwise and
marked as such) and in total, against every `max_words_*` constraint in the
case. On failure it lists the longest sentences of the over-limit part as
trim candidates. Fix the prose, re-run once, proceed. If the case names
required parts the counter cannot locate, they are reported `not_verifiable`
— verify them by reading, and say so in `result.json`.

### Step 2 — Render the editable artifact

```sh
python3 <skill-dir>/scripts/md2docx.py --md /app/output/introduction.md \
  --out /app/output/introduction.docx --title "Introduction" --verify
```

Produces a genuine OOXML docx (valid zip container with
`[Content_Types].xml`, `_rels`, `word/document.xml`, `word/styles.xml`;
headings, paragraphs, bullets, bold/italic/code runs). `--verify` re-opens
the package and parses the XML. Supported Markdown subset is documented in
the script docstring; anything outside it passes through as literal text —
inspect the preview (Step 3) to confirm nothing rendered wrong. If the case
requires a different native format, produce that format with the runtime's
tools instead and apply the same rule: real format, verified openable.

### Step 3 — Render an inspectable preview

```sh
python3 <skill-dir>/scripts/make_preview.py --md /app/output/introduction.md \
  --out-dir /app/output --title "Introduction"
```

Tries pdflatex/xelatex/tectonic, then matplotlib, then — honestly — a
plain-text preview with status `not_verifiable` when no PDF renderer exists.
The preview report records the renderer used. **Open the preview** (read it
back) and check: headings present, no missing paragraphs, citation markers
intact, no mojibake. A preview nobody looked at is not verification.

### Step 4 — Revision tasks: record every change

```sh
python3 <skill-dir>/scripts/change_record.py --old /app/work/v1.md \
  --new /app/output/introduction.md --out /app/work/changes.json \
  --rationale "<why these edits were made>"
```

Sentence-level diff records (added/modified/deleted, old, new, location,
rationale) shaped for `version_and_boundary.changes`. Records without a
rationale are flagged — fill them. Verify the diff preserves scientific
intent: revision must not change modality, causal strength, comparison
conditions or the meaning of attributed claims; if it does, that is a
scientific correction and must be labeled as such, not a copy edit.

### Step 5 — Assemble and self-check the delivery

Write `result.json` with all contract fields; put the word-budget report and
preview report into the `verification` field (or reference their paths, per
the contract's shape). Re-open every delivered file once: the docx (unzip and
glance at `word/document.xml` or convert to text), the preview, the JSON.
Keep original inputs intact.

## Exception handling

| Situation | Disposal |
|---|---|
| Required editable format unknown/unsupported | Deliver Markdown + the real docx, state the assumption in `version_and_boundary.open_items`, status `partial` |
| No PDF renderer in the runtime | Plain-text preview + `not_verifiable` preview report; do not claim a PDF exists |
| Over budget after trimming damages required content | Deliver the best within-budget version; record what was cut and why in changes/open_items; never silently exceed the limit |
| Revision old version missing | Treat as drafting task; record in open_items that no diff base existed |
| Case has no word constraints | Report counts with `not_verifiable` status; note the absence of limits |

## Limitations

- `word_budget.py` in cue mode is a heuristic — heading-structured drafts get
  exact accounting; free-flowing drafts get a labeled estimate to be confirmed
  by reading.
- `md2docx.py` implements a documented Markdown subset; complex constructs
  (tables, math) need the runtime's real converters — use them when present.
- The preview proves the artifact renders, not that the prose is correct.
- The bundled example under `examples/` is **synthetic** (invented material,
  interface demonstration only) — not an answer to any organizer case; binary
  artifacts it generates (docx/pdf) are regenerated by `run_example.sh` and
  are not shipped in the skill bundle.

## Files

- `scripts/word_budget.py` — per-part and total word budgets vs case constraints
- `scripts/md2docx.py` — Markdown → real OOXML docx (stdlib-only, self-verifying)
- `scripts/make_preview.py` — PDF/text preview with honest renderer reporting
- `scripts/change_record.py` — sentence-level change records with rationales
- `references/artifact_contract.md` — what "editable", "preview" and "verified" mean here
- `references/revision_records.md` — change-record discipline for revision tasks
- `examples/` — runnable synthetic end-to-end example (see `examples/README.md`)
