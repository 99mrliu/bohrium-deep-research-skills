# examples/minimal — synthetic end-to-end example

**Synthetic example / 合成示例，非正式案例结果。** The draft, glossary,
edits, and all outputs in `out/` are fabricated to demonstrate the
`termbase-gated-polish` pipeline; they are NOT results from a formal
evaluation case.

## What is in here

- `case.json` — synthetic case with `materials.glossary` (5 locked concepts:
  Li-ion battery/LIB, electrochemical impedance spectroscopy/EIS, solid
  electrolyte interphase/SEI, atomic layer deposition/ALD, NCM811) and an
  `output_contract` (`polished_text`, `changes`, `glossary`,
  `consistency_report`, `status`, `uncertainty`).
- `task.md` — the synthetic task statement.
- `source.md` — a synthetic electrochemistry short communication with 8
  planted terminology defects:
  1. title `Li-Ion` (wrong capitalization),
  2. `Lithium-ion batteries (LIBs)` (banned long form carrying the definition),
  3. `EIS` used in the Introduction but defined only in Methods (late definition),
  4. `li-ion` (lowercase),
  5. `Li ion` (missing hyphen),
  6. `solid-electrolyte interphase` (banned hyphenation, cross-section drift),
  7. `Lithium-ion diffusion` / `Li-ion and Lithium-ion cells` (banned variants, mixed in one sentence),
  8. `lithium ion batteries` (lowercase banned long form).
- `run.sh` — full pipeline: extract → agent review (deterministic stand-in)
  → lock → baseline lint (expected FAIL) → prepare → pre-set real edit batch
  (9 applied fixes + 1 deliberately unreviewed edit + 1 edit that would drop
  the protected token `2 nm`; both must be reverted) → apply → export →
  full-text lint gate → export with terminology report → result-skeleton →
  validate-result.
- `out/` — real artifacts produced by `sh run.sh` (see below).

## Run

```sh
cd examples/minimal && sh run.sh
```

Expected: exit code 0; the baseline lint reports 12 errors on the raw draft;
the post-edit lint reports **0 errors, gate PASS**; `result.json` validates
against the case `output_contract`.

## Outputs (out/)

| file | content |
|---|---|
| `termbase.json` | locked termbase (glossary + confirmed candidates, 0 conflicts) |
| `polished.md` | complete polished text with all 8 defects fixed |
| `changes.json` | 11 edit records: 9 applied, 2 reverted (missing review / lost protected token) |
| `audit.json` | unit/edit counts, guard statistics, SHA-256 hashes |
| `term-lint.json` | post-edit full-text scan (0 errors, 3 warnings) |
| `terminology-report.md` | human-readable terminology governance report |
| `result.json` | contract-mirrored, validated result |
