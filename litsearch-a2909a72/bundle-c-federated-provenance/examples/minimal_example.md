# Minimal invocation example (illustrative — NOT a formal case result)

The outputs below come from a local smoke test of this exact skill version against a
synthetic case and the live Crossref/OpenAlex/arXiv APIs. They illustrate the
interface; they are not results of any official test case.

## Input

`/input/case.json`:

```json
{"case_id": "TEST-CASE-000",
 "research_question": "Find recent literature on the stability and degradation mechanisms of halide perovskite solar cells (PSCs), especially moisture-induced degradation and defect passivation strategies.",
 "output_contract": {"candidate_literature": "...", "screening_evidence": "...", "status_report": "..."}}
```

`/app/work/queries.json` (agent-written after reading the case):

```json
[{"tag": "core", "query": "perovskite solar cell stability"},
 {"tag": "mechanism", "query": "halide perovskite moisture degradation"},
 {"tag": "strategy", "query": "perovskite defect passivation"}]
```

## Invocation

```
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status partial
python3 /skills/weekly-skill/scripts/federated_search.py --case /input/case.json --input /input --work /app/work --out /app/output --sources crossref,openalex,arxiv
python3 /skills/weekly-skill/scripts/dedup_verify.py --work /app/work --out /app/output --case /input/case.json
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status success
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --validate
```

## Illustrative digests (actual smoke-test output, auto-derived queries)

Fetch:

```json
{"FETCH_STATUS": "success", "pool_records": 146, "local_records": 0,
 "queries": 3, "query_origin": "auto-fallback", "degraded_sources": [],
 "source_summary": {"local-snapshot": "ok", "crossref": "ok", "openalex": "ok", "arxiv": "empty"}}
```

Dedup/verify (`--verify-n 5`):

```json
{"DEDUP_STATUS": "success", "raw_hits": 146, "canonical": 126,
 "multi_source_records": 18, "conflicts": 3,
 "doi_verified": 5, "doi_mismatch": 0, "doi_unreachable": 0}
```

Real conflict rows from the smoke test (kept visible, not silently resolved):

- `year`: kept 2026 (openalex) vs 2025 (arxiv) — the arXiv preprint predates the
  journal version of the same work.
- `venue`: kept "The Journal of Physical Chemistry Letters" (openalex) vs "arXiv"
  (arxiv) — same DOI, both sightings preserved in `provenance`.

## Illustrative outputs (files actually produced by the smoke test)

- `/app/output/candidates.md` — canonical records, multi-source sightings first,
  each with verification status.
- `/app/output/final_records.json` — full merged records with `ids`,
  `field_sources`, `provenance[]`, `verification`.
- `/app/output/provenance.jsonl` — one line per canonical record for auditing.
- `/app/output/dedup_report.md` — per-source inputs, merge arithmetic
  (146 raw = 126 canonical + 20 merged-away), conflict list, DOI verification sample.
- `/app/output/source_status.md` — per-source per-query status table.
- `/app/output/evidence/raw/*` — cached raw API responses.
- `/app/output/result.json` — validated: `VALIDATION OK: 3 contract fields filled`.
