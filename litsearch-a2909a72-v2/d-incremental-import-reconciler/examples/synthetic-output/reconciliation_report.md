# Reconciliation report — incremental-import-reconciler

- generated_at: `2026-11-25T07:41:04Z`
- mode: **incremental**
- state origin: `file:/Users/liuhengshen/Desktop/bhr_product/a2909a72-v2/bundles/d-incremental-import-reconciler/examples/synthetic-case/import_state.json` (2 entries)
- pool: 5 candidate(s) from 1 file(s); 0 file(s) skipped

## Counts

| action | count |
|-|-|
| ALREADY_IMPORTED | 1 |
| UPDATED | 1 |
| NEW | 1 |
| CONFLICT | 2 |
| SUSPECT | 0 |
| **total candidates** | 5 |

## Added (1)

- `10.0000/synth.d.003` fp `af6874cd7d90` — Idempotent upsert semantics for offline corpus snapshots (NO_STATE_MATCH)

## Updated (1)

- `10.0000/synth.d.002` (state key `doi:10.0000/synth.d.002`):
  - **year**: `2021` → `2020`

## Already imported — skipped (1)

- `10.0000/synth.d.001` fp `80e819bef090` — Incremental import reconciliation for scholarly knowledge bases (DOI_MATCH_IDENTICAL)

## Conflict queue — NOT imported, awaiting human resolution (2)

- **DOI_MATCH_TITLE_MISMATCH** on candidate `10.0000/synth.d.001`:
  - in state: title='Incremental import reconciliation for scholarly knowledge bases', doi='10.0000/synth.d.001', year=2022, venue='Journal of Synthetic Bibliometrics', fp `80e819bef090`
  - candidate: title='Incremental ingest harmonisation for scholarly knowledge bases', doi='10.0000/synth.d.001', year=2022, venue='Journal of Synthetic Bibliometrics', fp `69ccdaea91ca` (from /Users/liuhengshen/Desktop/bhr_product/a2909a72-v2/bundles/d-incremental-import-reconciler/examples/synthetic-case/snapshots/crossref_page1.json)
  - resolution requires a human: pick the authoritative identity, then re-run
- **TITLE_MATCH_DOI_MISMATCH** on candidate `10.0000/synth.d.777`:
  - in state: title='Provenance-aware deduplication in systematic literature pipelines', doi='10.0000/synth.d.002', year=2021, venue='Synthetic Review of Information Systems', fp `95319c5d9ce8`
  - candidate: title='Provenance-aware deduplication in systematic literature pipelines', doi='10.0000/synth.d.777', year=2021, venue='Synthetic Review of Information Systems', fp `12f5333c11e0` (from /Users/liuhengshen/Desktop/bhr_product/a2909a72-v2/bundles/d-incremental-import-reconciler/examples/synthetic-case/snapshots/crossref_page1.json)
  - resolution requires a human: pick the authoritative identity, then re-run

## Suspect — excluded with reason (0)

_none_

## Notes (honest)

- title-only matching (when a side lacks a DOI) is normalized string equality, not semantic matching
- conflicts are never auto-merged; the state is unchanged for every queued conflict
