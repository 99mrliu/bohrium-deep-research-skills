# Warden audit report — case SYNTH-E-001

- run audited: `/Users/liuhengshen/Desktop/bhr_product/a2909a72-v2/bundles/e-retrieval-run-warden/examples/synthetic-output/clean/run`
- timestamp: 2026-11-25T07:41:38.314479+00:00
- **overall GATE: PASS** (ERRORs: 0, WARNs: 2)

Every finding below names its evidence and how to re-check it by hand. The warden never modified the run directory; only result.json may have been rewritten (see --fix-result).

## Gate summary

| gate | status |
|-|-|
| ANTI-FABRICATION | PASS |
| FLOW | PASS |
| CONTRACT | PASS |
| ANOMALY | PASS |

## Recomputed counts (independent of run_log.jsonl)

- identified (records parsed from evidence copies): 4
- after_dedup (unique DOI/title keys): 3
- included (candidates shipped): 2

## Findings

### [WARN] ANOMALY — ZERO_HIT_TERMS
- query term(s) matched no record: mosquitoes, systems -- honest coverage gap, belongs in uncertainty
- re-check by hand: grep each term across examples/synthetic-output/clean/run/evidence

### [WARN] ANOMALY — SINGLE_SOURCE_POOL
- evidence pool has 1 file(s) / 1 source type(s) -- results rest on a single source
- re-check by hand: ls examples/synthetic-output/clean/run/evidence and note the source_type of each snapshot

## Evidence pool (re-hashed during this audit)

- `faad68f10bc0__crossref_page1.json` sha256_12=faad68f10bc0 bytes=2319
