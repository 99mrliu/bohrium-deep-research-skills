# Minimal invocation example (illustrative — NOT a formal case result)

The outputs below come from a local smoke test of this exact skill version against a
synthetic case and the live Crossref/OpenAlex APIs (EuropePMC was unreachable from the
test network, which is why it appears as a recorded source failure). They illustrate
the interface; they are not results of any official test case.

## Input

`/input/case.json`:

```json
{"case_id": "TEST-CASE-000",
 "research_question": "Find recent literature on the stability and degradation mechanisms of halide perovskite solar cells (PSCs), especially moisture-induced degradation and defect passivation strategies.",
 "output_contract": {"candidate_literature": "...", "screening_evidence": "...", "status_report": "..."}}
```

`/app/work/plan.json` (agent-written after reading the case):

```json
{"facets": [{"name": "perovskite", "terms": ["perovskite"], "expanded": ["halide perovskite", "PSC"]},
            {"name": "degradation", "terms": ["degradation", "stability"], "expanded": ["moisture-induced"]},
            {"name": "passivation", "terms": ["passivation", "defect"], "expanded": ["defect engineering"]}],
 "databases": ["crossref", "openalex"], "year_from": null, "year_to": null}
```

## Invocation

```
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status partial
python3 /skills/weekly-skill/scripts/planned_search.py --case /input/case.json --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status partial --uncertainty "EuropePMC unreachable"
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --validate
```

## Illustrative engine digest (actual smoke-test output, auto-fallback plan)

```json
{"ENGINE_STATUS": "success", "unique_records": 421, "local_ingested": 0,
 "snowball_new": 154, "uncovered_facets": [], "source_failures": ["europepmc"],
 "plan_origin": "auto-fallback", "stop_reason": "max rounds reached"}
```

With an agent-written `plan.json` the digest shows `"plan_origin": "agent-plan"` and
tighter top-ranked candidates.

## Illustrative outputs (files actually produced by the smoke test)

- `/app/output/candidates.md` — ranked top-30 with score, year, venue, DOI, sources.
- `/app/output/candidates.json` — all 421 unique records, each with `provenance[]`.
- `/app/output/search_report.md` — per-facet coverage, stop reason, failure list.
- `/app/output/evidence/search_log.jsonl` — one line per executed query with real URLs.
- `/app/output/evidence/raw/*.json` — cached API responses candidates trace back to.
- `/app/output/result.json` — `case_id: "TEST-CASE-000"`, all three `output_contract`
  fields filled with artifact paths, `sources` hashes of consulted inputs, the
  EuropePMC failure recorded in `uncertainty`; `--validate` prints
  `VALIDATION OK: 3 contract fields filled`.
