# Filling `/app/output/result.json` — output contract rules

`result.json` is the machine-readable verdict of the case. The **case's own
`output_contract` is the only schema that matters.** This file states the
rules; it does not define a fixed schema.

## Rule 1 — Read the real contract, never assume

- Open `/input/case.json` (and `/input/task.md`; `environment/resources.yaml`
  if present) at intake. Copy the real `case_id` verbatim — never invent or
  abbreviate one.
- Enumerate **every field** of the case's actual `output_contract` and fill
  each one. Field names, nesting, allowed values, and required formats come
  from the case file, not from this bundle and not from memory of other
  cases.
- If the case contract and this bundle's conventions differ, the case
  contract wins.

## Rule 2 — Early partial, atomic updates

- Write a **valid** `result.json` to `/app/output/` before any long work
  (right after intake), with status `partial` and a note of what is pending.
- Update it after each stage (extraction → glossary → translation → check →
  deliver). Write to a temp file and rename, so a crash never leaves a
  truncated JSON.

## Rule 3 — Honest status

- `success`: every requested deliverable produced; `lint_glossary.py` and
  `check_consistency.py` both exit 0; no unresolved `[待确认]` items hidden.
- `partial`: exactly state **what is missing and why** — which sections, which
  terms, which check still fails (ship the failing `glossary_check.json` as
  evidence), which source pages could not be extracted.
- `failed`: no usable deliverable; still record what was attempted and the
  blocking cause.
- Never claim `success` with a known defect. Never fabricate content,
  sources, or check results.

## Rule 4 — Sources, uncertainty, change record

- **Sources**: list the actual material files used (names/paths), the
  extraction method (e.g. `pdftotext`), and any external reference consulted
  for terminology decisions. This is the one-line fact & source mapping hook;
  the full ledger, if the case requires one, is a separate deliverable.
- **Uncertainty**: every `[待确认]` item from the glossary notes and the
  translation, each with location and the working choice made.
- **Change record**: `change_log.md` (and any field the contract provides)
  records version history — glossary entries added/changed mid-case, terms
  re-locked, sections re-translated after a failed check, and boundary
  decisions (what was deliberately left untranslated or out of scope).

## Rule 5 — Deliverable files

- `/app/output/` contains: the case-requested deliverable(s),
  `glossary.json`, `glossary_check.json`, `change_log.md`, `result.json`.
- Editable Office/slide/diagram artifacts additionally ship real PDF/PNG
  previews rendered from the artifact itself (not mock-ups).
- Paths listed inside `result.json` must point at files that actually exist
  at delivery time.
