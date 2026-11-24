# Filling `/app/output/result.json` — 输出契约填写规则

## 1. Read the real contract, never assume

- `result.json` is shaped by the case's ACTUAL `output_contract`, found in
  `/input/case.json` (and possibly refined by `/input/task.md`). Read it
  first, list EVERY field it declares, and fill each one. Never assume a
  schema from memory, from this bundle, or from another case.
- Use the real `case_id` from `/input/case.json` — verbatim, not paraphrased,
  not invented.

## 2. Save early, update atomically

- Write a valid partial `result.json` to `/app/output/result.json` BEFORE
  long work begins (even if most fields are placeholders marked as pending).
- After each stage (intake / extraction / translation / audit / delivery),
  rewrite it atomically: write to a temp file in the same directory, then
  rename over `result.json`. A crash must never leave a truncated JSON.
- Keep the JSON valid at all times (check with
  `python3 -m json.tool /app/output/result.json`).

## 3. Required content (adapt names to the real contract)

- `case_id`: the real one.
- Every field of the case's `output_contract`: filled with real content or,
  if impossible, an explicit reason.
- `status`: honest — `"done"` only when every deliverable exists and audits
  pass; `"partial"` stating exactly what is missing and why; `"failed"` with
  the blocking error. Never inflate.
- `sources`: the actual input material files used (paths/names from
  `/input/`), plus any tool outputs consulted.
- `uncertainty`: every `[待确认]` item, one entry each — source sentence,
  issue, provisional decision.
- `change_record` (or the contract's equivalent): summary of
  `change_log.md` — deviations from the hedge table, et al./等 convention,
  resolved findings, acknowledged findings, plus the one-line mentions for
  numbers / terminology / alignment.

## 4. Companion files expected alongside `result.json`

- The case-requested deliverable(s) (exact names/formats from the case).
- `boundary_ledger.jsonl`, `boundary_audit.json`, `citation_report.json`.
- `change_log.md` (every resolved/acknowledged finding).
- Editable Office/slide/diagram artifacts also need real PDF/PNG previews.

## 5. Honesty rule

A partial result that states precisely what is missing and why is always
acceptable. Fabricated translations, citations, reference entries, audit
results, or statuses are never acceptable.
