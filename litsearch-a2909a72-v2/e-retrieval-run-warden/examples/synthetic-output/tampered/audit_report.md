# Warden audit report — case SYNTH-E-001

- run audited: `/Users/liuhengshen/Desktop/bhr_product/a2909a72-v2/bundles/e-retrieval-run-warden/examples/synthetic-output/tampered/run`
- timestamp: 2026-11-25T07:41:54.265783+00:00
- **overall GATE: FAIL** (ERRORs: 3, WARNs: 2)

Every finding below names its evidence and how to re-check it by hand. The warden never modified the run directory; only result.json may have been rewritten (see --fix-result).

## Gate summary

| gate | status |
|-|-|
| ANTI-FABRICATION | FAIL |
| FLOW | FAIL |
| CONTRACT | PASS |
| ANOMALY | PASS |

## Recomputed counts (independent of run_log.jsonl)

- identified (records parsed from evidence copies): 4
- after_dedup (unique DOI/title keys): 3
- included (candidates shipped): 3

## Findings

### [ERROR] ANTI-FABRICATION — FABRICATION_SUSPECT
- DOI 10.0000/synth.e.phantom claimed by candidates.json rank=3 appears in NO evidence copy -- this identifier cannot be verified and must not ship
- re-check by hand: grep -riF '10.0000/synth.e.phantom' examples/synthetic-output/tampered/run/evidence  (expect zero matches)

### [ERROR] ANTI-FABRICATION — FABRICATION_SUSPECT
- title 'Phantom field trial of CRISPR gene drive eliminating malaria vectors entirely' claimed by candidates.json rank=3 appears in NO evidence copy -- this identifier cannot be verified and must not ship
- re-check by hand: grep -riF 'Phantom field trial of' examples/synthetic-output/tampered/run/evidence  (expect zero matches; the warden checks the title with all punctuation/case removed)

### [ERROR] FLOW — COUNT_MISMATCH
- run_log reports included=2 but independent recomputation from the evidence copies gives 3
- re-check by hand: re-parse every file in examples/synthetic-output/tampered/run/evidence and count records / unique dedup keys / candidates by hand

### [WARN] ANOMALY — ZERO_HIT_TERMS
- query term(s) matched no record: mosquitoes, systems -- honest coverage gap, belongs in uncertainty
- re-check by hand: grep each term across examples/synthetic-output/tampered/run/evidence

### [WARN] ANOMALY — SINGLE_SOURCE_POOL
- evidence pool has 1 file(s) / 1 source type(s) -- results rest on a single source
- re-check by hand: ls examples/synthetic-output/tampered/run/evidence and note the source_type of each snapshot

## Evidence pool (re-hashed during this audit)

- `faad68f10bc0__crossref_page1.json` sha256_12=faad68f10bc0 bytes=2319
