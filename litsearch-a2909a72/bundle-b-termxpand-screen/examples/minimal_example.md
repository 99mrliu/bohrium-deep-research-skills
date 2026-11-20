# Minimal invocation example (illustrative — NOT a formal case result)

The outputs below come from a local smoke test of this exact skill version against a
synthetic case and the live Crossref/OpenAlex APIs. They illustrate the interface;
they are not results of any official test case.

## Input

`/input/case.json`:

```json
{"case_id": "TEST-CASE-000",
 "research_question": "Find recent literature on the stability and degradation mechanisms of halide perovskite solar cells (PSCs), especially moisture-induced degradation and defect passivation strategies.",
 "output_contract": {"candidate_literature": "...", "screening_evidence": "...", "status_report": "..."}}
```

`/app/work/terms.json` (agent-written after reading the case):

```json
{"concepts": [{"name": "perovskite solar cell", "terms": ["perovskite solar cell", "PSC"],
               "expanded": ["halide perovskite", "钙钛矿太阳能电池"]},
              {"name": "stability", "terms": ["stability", "degradation"],
               "expanded": ["moisture", "lifetime", "稳定性"]},
              {"name": "passivation", "terms": ["passivation", "defect passivation"],
               "expanded": ["defect engineering", "缺陷钝化"]}],
 "databases": ["crossref", "openalex"], "year_from": null, "year_to": null}
```

## Invocation

```
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status partial
python3 /skills/weekly-skill/scripts/termxpand_screen.py --case /input/case.json --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status success
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --validate
```

## Illustrative engine digest (actual smoke-test output, auto-extracted concepts)

```json
{"ENGINE_STATUS": "success", "identified": 280, "screened": 265, "included": 6,
 "excluded_E1": 30, "excluded_E2": 229,
 "concepts": ["degradation", "moisture-induced", "passivation", "mechanisms",
              "perovskite", "strategies"],
 "queries": 7, "problems": []}
```

(With an agent-written `terms.json` including "solar cell" as a concept, inclusion is
sharper; the smoke test's `omissions.md` correctly surfaced four high-scoring E2
near-misses at 0.334–0.347, just below the 0.35 default, for one-threshold-review.)

## Illustrative outputs (files actually produced by the smoke test)

- `/app/output/screening_ledger.csv` — one row per record: decision, stage, reason
  code, score, evidence sentence. Example real row (E2 near-miss):
  `10.1007/s40843-022-2277-9 | "Strategies for enhancing the stability of metal halide
  perovskite towards robust solar cells" | excluded | abstract | E2 | score 0.338 < 0.35`
- `/app/output/prisma_flow.md` — identified 280 → duplicates 15 → screened 265 →
  E1 30 / E2 229 → included 6 (I1 3, I2 3).
- `/app/output/candidates.md` / `candidates.json` — ranked included set with scores.
- `/app/output/expansion_report.md` — every concept's expanded term set and the 7
  executed queries.
- `/app/output/omissions.md` — zero-coverage concepts + top E2 near-misses.
- `/app/output/result.json` — validated: `VALIDATION OK: 3 contract fields filled`.
