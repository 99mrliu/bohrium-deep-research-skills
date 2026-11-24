# Render Gate Report

- case_id: `synthetic-render-forge-001`
- gate: all rendered claims recomputed from data; hashes verified; no fabricated values

| # | check | result | detail |
|---|---|---|---|
| 1 | all contract fields present as keys in result.json | PASS | none |
| 2 | candidate count recomputed from data matches rendered claim | PASS | rendered=4 recomputed=4 |
| 3 | coverage matrix counts recomputed from data match rendered rows | PASS | rows compared: 10 |
| 4 | null contract fields consistent with unresolved_contract_fields | PASS | none |
| 5 | every artifact present with sha256 | PASS | 4 artifacts hashed |

gate_overall: PASS
