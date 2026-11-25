# Ranking report

Self-contained digest of the grading run. Machine-readable candidates: `graded_candidates.json`; human-verifiable decomposition: `graded_candidates.md`.

```json
{
 "ENGINE_STATUS": "success",
 "question": "Which publications report defect passivation strategies that improve the moisture stability of halide perovskite solar cells?",
 "facets_source": "agent-file:examples/synthetic-case/facets.json",
 "n_facets": 3,
 "facets": [
  {
   "name": "material",
   "terms": [
    "halide perovskite",
    "perovskite",
    "perovskite solar cell"
   ]
  },
  {
   "name": "problem",
   "terms": [
    "humidity",
    "moisture",
    "stability",
    "water-induced degradation"
   ]
  },
  {
   "name": "method",
   "terms": [
    "defect healing",
    "defect passivation",
    "passivation",
    "surface treatment"
   ]
  }
 ],
 "files_consulted": 1,
 "files_skipped": 0,
 "records_loaded": 5,
 "unique_records": 4,
 "duplicates_merged": 1,
 "grade_histogram": {
  "3": 1,
  "2": 2,
  "1": 0,
  "0": 1
 },
 "tiers": {
  "clear-include": 2,
  "borderline": 1,
  "clear-exclude": 1
 },
 "borderline_count": 0,
 "zero_hit_facets": [],
 "findings": [],
 "adjudications_applied": 1,
 "grades_changed": 1,
 "borderline_resolved_by_adjudication": 1,
 "ndcg_at_10_engine_vs_adjudication": 1.0
}
```

## Adjudication
Applied 1 adjudications (1 changed an engine grade); see `adjudication_ledger.md`. Engine-vs-adjudication nDCG@10 = 1.0000 (self-consistency, not a benchmark score).

