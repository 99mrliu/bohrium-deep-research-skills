---
name: termbase-forge
description: Academic translation & bilingual writing (EN↔ZH) with terminology asset engineering (术语资产工程) at its center: extract a termbase from the actual source, curate a locked bilingual glossary with discipline disambiguation, and deterministically enforce one-source-term-one-translation (术语锁定) across abstract, body, captions, and appendix.
---

# termbase-forge — 术语资产工程 for academic translation

## Purpose

Full academic translation cases fail most often on **terminology drift**: the
same source term rendered three different ways across abstract, body, captions,
and appendix. This skill makes terminology a first-class, machine-checked
asset (术语资产):

1. **Extract** a candidate termbase from the *actual* source text
   (`scripts/extract_terms.py` → `terms_draft.json`).
2. **Curate** a locked bilingual glossary (`glossary.json`) with discipline
   disambiguation (e.g. cell = 电池 electrochemistry / 细胞 biology) and a
   first-mention convention (中文全称（English full name, ABBR）).
3. **Translate** with the glossary as the single source of truth (the agent
   does the translation; the scripts only verify).
4. **Enforce** the lock deterministically (`scripts/check_consistency.py` →
   `glossary_check.json`): one source term = exactly one translation, in every
   section, including captions and appendix.

Other case machinery (numeric/fact ledgers, sentence alignment, boundary
records) is handled elsewhere: numbers and facts are recorded in the case's
fact & source mapping, alignment belongs to the bilingual deliverable format,
and boundary/change records go into `change_log.md` and `result.json`. This
skill owns the **term layer** only — one line each, do not duplicate.

## Trigger conditions

Use this skill when a case asks for: EN↔ZH academic translation, bilingual
(双语对照) writing, abstract/paper/caption translation, terminology/glossary
(术语表) work, or any deliverable where consistent technical terminology is
graded. If the case has no translation component, do not use this skill.

## Invocation

The platform installs this bundle as an agent Skill. The scripts are pure
Python 3 stdlib (no pip, no network):

```bash
python3 scripts/extract_terms.py SOURCE.txt -o terms_draft.json
python3 scripts/lint_glossary.py glossary.json [--json]
python3 scripts/check_consistency.py glossary.json SOURCE.txt TRANSLATION.md -o glossary_check.json
```

Exit codes: `lint_glossary.py` and `check_consistency.py` exit non-zero on any
error and always print a human-readable report; treat non-zero as a blocking
defect to fix before delivery.

## Full case workflow

### 0. Intake (mandatory, before any translation)

Follow the Runtime contract below: read the case files, identify deliverables,
language direction (EN→ZH or ZH→EN), and the real `output_contract`. Read the
actual material files yourself — a PDF has no pre-extracted answer layer;
extract text with `pdftotext` (available) and work from that. Write the
extracted plain text to `/app/work/source_extracted.txt`.

### 1. Term extraction

```bash
python3 scripts/extract_terms.py /app/work/source_extracted.txt -o /app/work/terms_draft.json
```

Review the draft: acronyms, capitalized compounds, hyphenated compounds, and
frequent content n-grams, each with count, section histogram, and example
contexts. The draft is a *candidate list*, not a glossary — expect noise
(e.g. headings, function-word residues) and gaps (single unigram terms like
"cell" are not surfaced as n-grams; add them manually when discipline-
sensitive).

### 2. Glossary curation (the lock)

Hand-curate `glossary.json` from the draft plus your own reading of the
source. One entry per source term, schema:

```json
{"source": "...", "target": "...", "note": "...", "discipline": "...",
 "first_mention": "中文全称（English full name, ABBR）",   // optional
 "forbidden_variants": ["..."]}                            // optional
```

Rules (full detail in `references/method.md`):

- **One term, one translation (术语锁定).** Choose the single target rendering
  per source term for this case and record it. List plausible-but-rejected
  renderings in `forbidden_variants`.
- **Discipline disambiguation.** Record the chosen sense in `discipline`
  (cell = 电池 in electrochemistry vs 细胞 in biology; bond = 化学键 in
  chemistry vs 债券 in finance). When the source itself is ambiguous, do not
  silently pick: mark the entry note and the case uncertainty log with
  `[待确认]`.
- **First-mention convention.** On first use in the target text write
  `中文全称（English full name, ABBR）`, then use the abbreviation or the
  locked short form. Store that exact string in `first_mention`.
- **Source-internal inconsistency.** If the source itself uses two forms for
  one concept, pick the dominant form as the key, record the discrepancy with
  `[待确认]` in `note` and in the case uncertainty log. Never silently
  normalize away a discrepancy.
- **Captions and appendix inherit the lock.** No exceptions, no "figure
  shorthand".

Validate before translating: `python3 scripts/lint_glossary.py glossary.json`
must exit 0.

### 3. Locked translation (by the agent)

Translate section by section (abstract → body → captions → appendix), saving
per-section drafts under `/app/work/` as you go. Every glossary term MUST be
rendered with its locked target, first mention expanded per `first_mention`,
then the abbreviation/short form. Register any term discovered mid-translation
back into `glossary.json` (append, then re-lint) — never improvise a second
rendering of an existing entry.

### 4. Consistency enforcement

```bash
python3 scripts/check_consistency.py glossary.json source_extracted.txt translation.md -o glossary_check.json
```

Every checked term must be `locked_ok` (or `ok_with_warnings` with each
warning explained in `change_log.md`). Any error — `forbidden_variant`,
`section_lock_violation`, `untranslated_leak` — blocks delivery: fix the
translation (not the script) and re-run until exit 0.

### 5. Deliver

Assemble the case-requested deliverable(s) (clean target-language version
and/or bilingual aligned version, per the case), plus `glossary.json`,
`glossary_check.json`, `change_log.md`, and `result.json` filled per
`references/output_contract.md`. Numbers/facts: cite the case fact & source
mapping (one line). Alignment: keep the bilingual pairing format the case
requests (one line). Boundaries: log untranslated leftovers and `[待确认]`
items (one line).

## Inputs / Outputs

**Inputs** (from the case): source material files (PDF/TXT/MD), `case.json`,
`task.md`, optional `environment/resources.yaml`.

**Outputs** (to `/app/output/`):

| File | Content |
|---|---|
| case deliverable(s) | clean target-language and/or bilingual aligned version, exactly as the case requests |
| `glossary.json` | the locked bilingual glossary (lint-clean) |
| `glossary_check.json` | machine verdict from `check_consistency.py`, exit 0 |
| `change_log.md` | version & boundary record: what was decided, changed, left out, `[待确认]` items |
| `result.json` | per `references/output_contract.md` |

Intermediate artifacts (`terms_draft.json`, extracted text, per-section
drafts) live in `/app/work/`.

## Exception handling

- **Unreadable/scanned PDF**: try `pdftotext`; if the text layer is garbage,
  state `partial` in `result.json` with exactly which pages/sections could not
  be extracted. Never invent source content.
- **Ambiguous term / conflicting senses**: record `[待确认]` in the glossary
  `note` and in `result.json` uncertainty; choose the dominant-discipline
  sense only as a documented working choice.
- **check_consistency cannot reach exit 0**: deliver `partial`, ship
  `glossary_check.json` showing the residual errors, and explain each in
  `change_log.md`. Do not delete failing entries to force a pass.
- **Case asks for something outside this skill** (e.g. fact-ledger formats):
  follow the case's own contract; this skill only adds the term layer.

## Runtime contract

- First read `/input/case.json` and `/input/task.md` (and
  `environment/resources.yaml` if present); record the actual `case_id`, the
  requested deliverables, the language direction, and EVERY field of the real
  `output_contract` — never assume its schema. Read the actual material
  files; a PDF has no pre-extracted answer layer — extract it yourself
  (`pdftotext` is available).
- Create `/app/work` and `/app/output`. Save a valid EARLY partial
  `/app/output/result.json` before long work; update it atomically after each
  stage. Budget: 64 model requests / 900 s — run the deterministic scripts
  early, save per-section.
- Final `/app/output`: the case-requested deliverable(s), `glossary.json`,
  `glossary_check.json`, `change_log.md`, and `result.json` with the real
  `case_id`, all actual `output_contract` fields, an honest
  success/partial/failed status, sources, uncertainty, and change records.
  Editable Office/slide/diagram artifacts also need real PDF/PNG previews.
  A partial result states exactly what is missing and why. Never fabricate.

## References

- `references/method.md` — terminology rules (locking, disambiguation,
  first-mention, source inconsistency, caption/appendix inheritance).
- `references/output_contract.md` — how to fill `/app/output/result.json`.
- `examples/synthetic/` — a small fully synthetic worked example
  (合成示例 / synthetic example) with actual script outputs.
