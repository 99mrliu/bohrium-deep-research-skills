# KG delivery report — `SYNTH-DEMO-001`

> ⚠ **SYNTHETIC example output** — demonstrates the deliverable set only; NOT a real-paper answer.

produced by `e-kg-delivery-studio/1.0` · stdlib-only deterministic layout · 25 nodes / 27 edges / 1 merges / 1 non-merges / 1 conflicts preserved

## Full graph

see `graph.svg` (25 nodes, 27 edges)

## Queries

### q1 — neighborhood (ok)

- params: `{"depth": 1, "node": "MAPbI3"}`
- svg: `query_q1.svg`
- result: 5 node(s), 4 edge(s)
- undetermined: **hysteresis index** — unreported in the corpus: Neither paper reports a hysteresis index; S1 explicitly states it was not measured and S2 states hysteresis behavior was not assessed.

### q2 — relation (ok)

- params: `{"relation": "measures"}`
- svg: `query_q2.svg`
- result: 6 node(s), 5 edge(s)
- undetermined: **hysteresis index** — unreported in the corpus: Neither paper reports a hysteresis index; S1 explicitly states it was not measured and S2 states hysteresis behavior was not assessed.

### q3 — path (ok)

- params: `{"check_conflicts": true, "from": "champion MAPbI3 device", "max_len": 3, "to": "aged MAPbI3 device"}`
- svg: `query_q3.svg`
- result: 9 node(s), 11 edge(s)
- path: N06 → N01 → N08
- conflict preserved on power conversion efficiency (PCE): 18.7%, 19.3%, 21.1% (resolution=preserved)
- undetermined: **hysteresis index** — unreported in the corpus: Neither paper reports a hysteresis index; S1 explicitly states it was not measured and S2 states hysteresis behavior was not assessed.

## Merges / non-merges / unreported
- MERGE N01 <- N02 (key `mapbi3`): S2's 'MAPbI3' is the abbreviation defined in S1 as 'methylammonium lead iodide (MAPbI3)'; same absorber material across papers (alias merge).
- NON-MERGE N03 ≠ N04 (key `tio2`): Both normalize to 'TiO2' but S1's is a compact spray-pyrolyzed electron transport layer while S2's is a mesoporous screen-printed scaffold; s2p09 states compact TiO2 was not evaluated in S2. Same name, different physical objects: explicit NON-merge.
- UNREPORTED: hysteresis index — Neither paper reports a hysteresis index; S1 explicitly states it was not measured and S2 states hysteresis behavior was not assessed.

## Evidence index

53/53 quotes mechanically re-verified as exact substrings; full table in `report.html` and `evidence_index.json`.
