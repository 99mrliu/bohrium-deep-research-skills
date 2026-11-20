# Methodology — federated fetch, dedup and verification

Exact rules implemented by `scripts/federated_search.py` and `scripts/dedup_verify.py`,
so every record, merge and conflict can be defended or reproduced.

## 1. Source adapters

| Source | Endpoint | Query parameter | Notes |
|-|-|-|-|
| Crossref | `api.crossref.org/works` | `query.bibliographic` | richest DOI metadata; polite `select` field list |
| OpenAlex | `api.openalex.org/works` | `search` | abstracts via inverted-index reconstruction; citation counts |
| EuropePMC | `www.ebi.ac.uk/europepmc/webservices/rest/search` | `query` | biomedical; PMID tracked as a second id |
| arXiv | `export.arxiv.org/api/query` | `search_query=all:"w1" AND ...` (first 6 words) | preprints; Atom XML parsed with stdlib ElementTree |
| local-snapshot | `/input/**/*.json` | — | saved Crossref/EuropePMC/OpenAlex responses or reference lists; organizer-provided, always authoritative |

Each adapter is independent: its failure (timeout, HTTP error, parse error) is caught,
recorded with status `timeout`/`error` (or `empty` for a clean zero-hit), and never
aborts the other sources. One retry with backoff, then the failure stands — repeated
hammering is worse than an honest gap.

Every raw response body is cached (≤400 KB) under `/app/output/evidence/raw/`; each
pooled record's provenance points at its cache file, source, query string, full URL
and UTC retrieval time.

## 2. Normalized schema

`{title, authors[], year, venue, doi, abstract, cited_by, type, url, ids{doi?,
openalex?, pmid?, arxiv?}, provenance[]}`. Missing values stay `null` — never
synthesized. DOIs are lowercased and stripped of the `https://doi.org/` prefix at
ingest so cross-source matching works.

## 3. Deduplication (union-find clustering)

1. **Exact pass:** records sharing a DOI are merged unconditionally.
2. **Fuzzy pass:** records are bucketed by the first 25 chars of the normalized title
   (`[a-z0-9 ]` only); within a bucket, pairs with difflib ratio ≥ 0.92 (adjustable via
   `--title-threshold`) are merged — **unless both records carry DOIs and those DOIs
   differ**: two different DOIs are two different publications even when titles match
   (paper vs. supporting-information DOI is the common case). Bucketing keeps this
   O(n·k) instead of O(n²).

## 4. Merge semantics

- Field priority: `local-snapshot > crossref > openalex > europepmc > arxiv` — the first
  non-empty value in that order wins each field, and `field_sources` records the winner.
- `cited_by` takes the maximum across sources (counts are source-specific; the max is
  the most informative single number and its source is implied by the value).
- **Conflicts:** when a later source supplies a *different* non-empty value for
  `title/year/venue/doi`, both values and both sources are logged to
  `dedup_report.md`. The canonical record keeps the priority winner; the disagreement
  stays visible.
- All ids from all sightings are unioned into `ids`; all provenance entries are
  concatenated. Invariant: `raw hits = canonical records + merged-away sightings`.

## 5. Verification

A bounded sample (default 15, `--verify-n`) of canonical DOIs is re-fetched from
`api.crossref.org/works/{doi}`:

- `verified`: endpoint answered and the returned title matches the canonical title
  (difflib ≥ 0.8).
- `metadata-mismatch`: endpoint answered but the title differs — the record is flagged,
  not silently "corrected".
- `unreachable`: network/HTTP failure — stated, never treated as valid.
- `no-doi` / `not-checked`: honest states for the remainder.

## 6. Ordering

`candidates.md` sorts by (1) number of source sightings descending — cross-source
corroboration is the strongest cheap quality signal — then (2) a lexical relevance
score: `0.8 * (fraction of ≤12 question terms in title+abstract) + 0.2 *
log-normalized citations`. Simple on purpose: every position is explainable.

## 7. Failure semantics

- Fetch digest `FETCH_STATUS: partial` whenever any source degraded; the degraded set
  is named. Dedup runs fine on whatever the pool contains, including the
  local-snapshots-only (`--offline`) case (`--no-verify` then).
- Nothing in the pipeline fabricates records, ids, verification states or metadata.
