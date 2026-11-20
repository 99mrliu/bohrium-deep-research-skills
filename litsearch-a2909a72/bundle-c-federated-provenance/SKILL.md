---
name: litsearch-federated-provenance
description: Federated multi-database literature retrieval with deduplication, per-field provenance and DOI verification. Two stdlib-only scripts form the pipeline: federated_search.py queries Crossref/OpenAlex/EuropePMC/arXiv through independent adapters plus any local snapshots under /input, caches every raw API response, and reports each source's status (ok/empty/timeout/error) so degraded runs are visible; dedup_verify.py then clusters duplicate records across sources (exact DOI + fuzzy title >= 0.92), merges them into canonical records keeping which source supplied each field, logs metadata conflicts, and verifies a bounded DOI sample against Crossref. A contract-driven builder fills every output_contract field. Use for literature-search cases (学术文献检索) where result quality means traceable sources, accurate merged metadata, honest source-failure reporting and reviewer-reproducible dedup, within ~8-12 model requests.
---

# Literature retrieval as federated search + provenance verification

Philosophy: **a literature list is only as trustworthy as its provenance chain.** Base agents fail these cases by querying one source, mixing duplicates (the same paper from Crossref, OpenAlex and arXiv appears three times with conflicting metadata), and leaving no way to check where any record came from. This skill treats retrieval as a federation problem: independent source adapters with per-source status, raw-response caching, cross-source dedup with per-field merge provenance, conflict logging, and DOI verification. You supply judgment (the queries); the scripts guarantee integrity.

## Inputs and outputs

- Read first: `/input/case.json` (note `case_id` and **every** field in `output_contract`), `/input/task.md`, and `ls -R /input` — organizer snapshots (saved Crossref/EuropePMC/OpenAlex responses, reference lists) are ingested as a first-class source and are authoritative.
- Work in `/app/work`; deliverables to `/app/output` including `result.json` with the original `case_id` and every `output_contract` field.
- Secure a partial `result.json` first; budget target ≤12 model requests.

## Procedure

1. **Secure a partial result:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status partial
   ```

2. **Write 2–4 queries — your one high-value act.** After reading the case, write `/app/work/queries.json`:

   ```json
   [{"tag": "core", "query": "perovskite solar cell stability"},
    {"tag": "mechanism", "query": "halide perovskite degradation moisture"},
    {"tag": "zh-expansion", "query": "钙钛矿 稳定性"}]
   ```

   Cover the question's distinct sub-topics and language variants; keep each query 3–8 words (adapters quote/AND them as appropriate). If you skip this, the fetcher derives queries automatically — worse; note it in `uncertainty`.

3. **Fetch from all sources:**

   ```
   python3 /skills/weekly-skill/scripts/federated_search.py --case /input/case.json --input /input --work /app/work --out /app/output
   ```

   Digest: `FETCH_STATUS`, pool size, degraded sources. Writes `/app/work/pool.json` (every raw hit with `{source, query, url, raw, retrieved_at}` provenance), `/app/output/source_status.md`, `/app/output/evidence/fetch_log.jsonl`, and cached raw responses under `evidence/raw/`. Choose sources with `--sources crossref,openalex,europepmc,arxiv` (default all four; EuropePMC only helps biomedical topics, arXiv only helps physics/CS/math).

4. **Deduplicate, merge, verify:**

   ```
   python3 /skills/weekly-skill/scripts/dedup_verify.py --work /app/work --out /app/output --case /input/case.json
   ```

   Digest: raw hits → canonical records, multi-source records, conflicts, DOI verification tally. Writes `final_records.json`, `candidates.md` (multi-source records first — a paper found by 3 sources outranks a single-source hit), `provenance.jsonl` (one line per canonical record: ids, field-level sources, verification, all sightings), `dedup_report.md` (per-source input counts, merges, conflicts, verification sample).

5. **Verify the digest, then finalize:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status success
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --validate
   ```

   Check `source_status.md`: any source not `ok`/`empty` is a real degradation — copy it into `uncertainty` via `--uncertainty "EuropePMC unreachable (timeout)"` and use `status` `partial` if a source was material to the topic. Check `dedup_report.md` conflicts: they are reported, not resolved silently — the kept value and its source are shown.

## What the pipeline guarantees (and what you must not break)

- **Raw evidence retention:** every fetched response is cached under `evidence/raw/`; every canonical record's `provenance` lists all source sightings with the exact query URL. Reviewers can re-issue any query.
- **Lossless dedup:** merged-away copies are never deleted — they persist inside `provenance` and are counted in `dedup_report.md`. The arithmetic `raw hits = canonical + merged away` always holds.
- **Per-field honesty:** `field_sources` records which source supplied the title/year/venue/DOI; when sources disagree (e.g. different years for the same DOI) both values and both sources appear in the conflict list.
- **No fabrication:** records come only from real responses or local snapshots; missing metadata is `null`; unverifiable DOIs are marked `unreachable`, not assumed valid.
- **Bounded verification:** at most `--verify-n` (default 15) DOIs are checked to respect the time budget; the rest are marked `not-checked` — do not claim full verification.

## Exception handling

| Situation | Handling |
|-|-|
| One source fails (timeout/HTTP) | It is logged in `source_status.md` and the pool continues without it. Note in `uncertainty` if that source was topically material; do not retry more than once. |
| No network at all | Re-run fetch with `--offline`: only local snapshots are pooled; then run dedup with `--no-verify`. Status `partial`; state the outage plainly. |
| Empty pool | Check query derivation in the digest; write better `queries.json` (shorter, English terms) and re-run once. If still empty, keep `status=partial` and list the tried queries (they are in `fetch_log.jsonl`). |
| Rate limiting (HTTP 429) | Remove the affected source via `--sources` and re-run once; record it. |
| arXiv XML parse error | Logged as that query's status; other sources unaffected. |
| Suspicious merge (two different papers merged) | Lower sensitivity by raising `--title-threshold` toward 0.96 and re-run dedup once; mention the adjustment in the report. |

## Resources

- `scripts/federated_search.py` — adapters + local-snapshot ingest + raw caching + source status. Stdlib only.
- `scripts/dedup_verify.py` — clustering, per-field merge, conflict log, DOI verification.
- `scripts/make_result.py` — output_contract-driven result.json builder/validator.
- `resources/methodology.md` — adapter details, dedup keys and thresholds, merge priority, verification semantics.
- `resources/selfcheck.md` — final checklist.
- `examples/minimal_example.md` — minimal end-to-end invocation with illustrative (clearly marked) output.

## Limits

- Fuzzy title matching (difflib ≥0.92) can merge near-identical titles of genuinely different papers (e.g. "…: part I/II"); the conflict list exposes these for review rather than hiding them.
- DOI verification samples ≤15 records; `not-checked` is the honest state of the rest.
- Ranking is a simple multi-source-presence + lexical relevance order, not a learned model — designed for auditability, not maximal nDCG.
- Full-text access and paywalled metadata are out of scope; say so when the task requires them.
