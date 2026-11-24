# Coverage ledger — synthetic-intro-demo-0001

Status: **pass**

## Coverage checklist

| # | check | result | detail |
|---|---|---|---|
| 1 | distinct citations >= 4 | PASS | 6 distinct refs cited: synth01, synth02, synth03, synth04, synth05, synth06 |
| 2 | topic covered: "template-based binding-site prediction" | PASS | cited candidates: synth01, synth02, synth06 |
| 3 | topic covered: "sequence-only binding-site prediction" | PASS | cited candidates: synth02, synth06, synth01 |
| 4 | topic covered: "multi-structure consensus scoring" | PASS | cited candidates: synth05, synth01, synth03 |
| 5 | top-2 closest works cited | PASS | ranking: synth01(6), synth02(5), synth06(5), synth03(3) |
| 6 | recency | PASS | cited years: 2019 x1, 2020 x1, 2021 x1, 2022 x1, 2023 x1, 2024 x1 |
| 7 | no decorative citations | PASS | no suspicious clusters |
| 8 | no uncited bibliography entries | PASS | all entries cited |

## Closest-work ranking (overlap with problem statement)

- synth01: overlap 6 shared: binding, identity, ligand, site, target, template
- synth02: overlap 5 shared: binding, sequence, site, target, template
- synth06: overlap 5 shared: binding, identity, sequence, site, template
- synth03: overlap 3 shared: identity, target, template
- synth04: overlap 3 shared: binding, identity, template
- synth05: overlap 3 shared: protein, target, template

Heuristic notice: topic mapping, closest-work ranking and the
decorative lint use lexical overlap only; the writer must confirm
semantic relevance by reading the provided reference texts.
