# Terminology Governance Report

> Synthetic example output / 合成示例产物, not a formal case result

- Source SHA-256: `165c7c77fa4335a005acc5d8d778b009849d690f95bfa05ffeabf310d95cfd3d`
- Polished SHA-256: `471a7624b04e63c31fa2e53b5f28ba944a0eae6f6a684f0aa5688dfeb0c69eac`
- Termbase entries: 5 | Conflicts: 0
- Full-text lint: **0 errors, 3 warnings — gate PASS**

## Locked termbase

| id | canonical | abbrev | variants | banned | first-use policy | origin |
|---|---|---|---|---|---|---|
| t0001 | Li-ion battery | LIB | Li-ion batteries, Li-ion cell, Li-ion cells, Li-ion, LIBs | Lithium-ion, Lithium-ion battery, Lithium-ion batteries, Lithium-ion cell, Lithium-ion cells | define_at_first_use | glossary+confirmed |
| t0002 | electrochemical impedance spectroscopy | EIS | — | EIS spectroscopy, electrochemical impedance spectra | define_at_first_use | glossary+confirmed |
| t0003 | solid electrolyte interphase | SEI | — | solid-electrolyte interphase, solid electrolyte interface | define_at_first_use | glossary+confirmed |
| t0004 | atomic layer deposition | ALD | — | — | define_at_first_use | glossary+confirmed |
| t0005 | LiNi0.8Co0.1Mn0.1O2 | NCM811 | — | — | define_at_first_use | glossary+confirmed |

## Conflicts

None. The locked termbase is internally consistent.

## Full-text lint findings

| id | severity | type | term | surface | location | message |
|---|---|---|---|---|---|---|
| f0001 | warning | abbrev_defined_but_unused | t0001 | LIB | Introduction L5 | abbreviation 'LIB' is defined but never used afterwards; consider dropping the abbreviation |
| f0002 | warning | abbrev_defined_but_unused | t0005 | NCM811 | Methods L9 | abbreviation 'NCM811' is defined but never used afterwards; consider dropping the abbreviation |
| f0003 | warning | abbrev_defined_but_unused | t0004 | ALD | Methods L9 | abbreviation 'ALD' is defined but never used afterwards; consider dropping the abbreviation |

## Notes and boundaries

- The gate is mechanical: it proves the absence of *registered* defects, not the absence of all terminology problems. Terms absent from the termbase are not checked.
- Candidate extraction and matching are heuristic (see references/glossary-governance.md); borderline matches need human confirmation.
- Findings above are byte-position deterministic; re-running on identical input reproduces them exactly.
