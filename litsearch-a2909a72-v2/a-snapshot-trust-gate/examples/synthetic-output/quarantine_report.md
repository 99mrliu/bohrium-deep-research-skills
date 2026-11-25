# Quarantine & trust report

Every snapshot file under --input/--corpus was hashed, parsed and schema-checked BEFORE any record entered the corpus.

## Quarantined (excluded from corpus)
- `snapshots/crossref_page1_duplicate.json` — **DUPLICATE_PAYLOAD**; duplicate of `snapshots/crossref_page1.json` (sha256:d1ed4d22424a)
- `snapshots/mystery.json` — **SCHEMA_UNRECOGNIZED** (sha256:657a07fc2e41)
- `snapshots/truncated_response.json` — **PARSE_ERROR**; Unterminated string starting at: line 5 column 48 (char 97) (sha256:a72826c003c6)

## Verified snapshots

| file | source type | records | flagged records | trust tier | sha256 |
|-|-|-|-|-|-|
| snapshots/crossref_page1.json | crossref | 3 | 1 | T2-flagged-records | d1ed4d22424a |
| snapshots/europepmc_page1.json | europepmc | 2 | 0 | T1-verified | 324198ea1eb8 |
