# Glossary Governance — schema, execution order, conflict policy, heuristic limits

This file is the authoritative reference for the termbase used by
`scripts/termbase.py`. Read it before reviewing candidates or editing a
glossary.

## 1. Termbase entry schema

One JSON object per locked concept:

| field | type | meaning |
|---|---|---|
| `id` | string | assigned by `lock` (`t0001`...), stable per run |
| `canonical` | string | the ONE registered full form, e.g. `"Li-ion battery"` |
| `abbrev` | string \| null | registered abbreviation, e.g. `"LIB"`; null if none |
| `variants` | string[] | additional *allowed* surfaces (plurals, short forms, abbrev plural `"LIBs"`) |
| `banned` | string[] | surfaces that must NOT appear (deprecated long forms, wrong hyphenation) |
| `first_use_policy` | string | `"define_at_first_use"` or `"none"` |
| `origin` | string | `glossary`, `confirmed`, or `glossary+confirmed` |
| `note` | string | free-text rationale from the case owner / agent |

Rules of thumb when writing entries:

- `canonical` is the full form you want in the text; sentence-initial
  capitalization of its first letter and title-case inside headings are
  tolerated automatically by `lint`.
- Put inflections you accept into `variants` (plural, `cell`/`cells`,
  short form `"Li-ion"`). Put inflections you reject into `banned`
  (`"Lithium-ion"`, `"solid-electrolyte interphase"`).
- Matching is hyphen/space-insensitive and case-aware: a surface whose
  normalized form (lowercase, hyphens/spaces stripped) equals a registered
  one but whose exact casing differs is a `spelling_inconsistency` error.
  Banned matching uses the same normalization, so `"lithium ion batteries"`
  is caught by banning `"Lithium-ion batteries"`.

## 2. Execution order (non-negotiable)

1. `extract` — mine candidates from the draft.
2. Agent review — confirm real terms, clean `canonical_guess`, drop noise;
   emit `{"confirmed": [...]}`. This review IS the method: heuristics
   propose, the agent disposes.
3. `lock` — merge glossary + confirmed entries into `termbase.json`.
   Conflicts halt the pipeline.
4. (Recommended) baseline `lint` of the untouched draft → defect checklist.
5. Edit via `pipeline.py` (reviewed batches only).
6. `lint` the polished text → must pass with 0 errors before export is final.

Never edit before `lock`; never export before the post-edit `lint` passes.

## 3. Conflict handling

`lock` detects and reports, never reconciles:

| conflict type | trigger | resolution |
|---|---|---|
| `same_abbrev_two_full_names` | glossary says `EIS = electrochemical impedance spectroscopy`, candidate claims `EIS = electron imaging system` | ask the case owner; if unresolvable, exclude the candidate and note in `uncertainty` |
| `same_full_name_two_abbrevs` | two abbreviations for one canonical | keep the glossary abbreviation; record the other in `banned` if it must not appear |

Exit code 1 from `lock` means: the termbase is not safe; editing on top of it
would bake the conflict into the text. Deliver partial if you cannot resolve.

## 4. Extraction heuristics and their boundaries

`extract` emits three candidate kinds:

- **abbrev_pair**: `Full Name (ABBR)` patterns. The full name is guessed by
  taking trailing words whose initials cover the abbreviation letters
  (subsequence match). Boundary errors happen with long lead-ins
  ("deposited by atomic layer deposition (ALD)") — the guess is usually
  right, but CHECK it.
- **acronym**: ALL-CAPS tokens (length ≥ 2, e.g. `EIS`, `NCM811`). Frequency
  is reported; an acronym used once is often undefined. The extractor cannot
  invent its full name — if the draft never expands it, either the domain
  knowledge of the agent supplies the expansion (record the source in
  `note`) or the term stays out of the termbase and the gap goes into
  `uncertainty`.
- **multiword**: frequent bigram/trigram noun phrases after stopword
  filtering. High noise; confirm only genuine technical terms.

Known limits:

- Sentence splitting and matching are ASCII-oriented; CJK text is passed
  through but phrase mining is tuned for English drafts.
- Chemical formulas with internal digits (`Al2O3`) are intentionally not
  treated as acronyms.
- `lint` checks registered entries only. An unregistered term can still be
  inconsistent — that is what the final human read is for.

## 5. Lint finding types

| type | severity | meaning |
|---|---|---|
| `banned_variant` | error | a banned surface appears |
| `spelling_inconsistency` | error | normalized form registered, exact casing/hyphenation not |
| `late_definition` | error | abbreviation used before its `Full Name (ABBR)` definition |
| `never_defined` | error | abbreviation used, full name absent everywhere |
| `definition_uses_banned_variant` | error | definition exists but phrases the full name with a banned variant |
| `cross_section_drift` | error | inconsistencies of one entry span multiple sections, or sit outside every section where its registered full form appears |
| `abbrev_defined_but_unused` | warning | abbreviation defined but never used again (consider dropping it) |
