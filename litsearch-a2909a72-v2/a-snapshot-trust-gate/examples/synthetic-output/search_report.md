# Search report (snapshot-trust-gate)

```json
{
 "ENGINE_STATUS": "success",
 "question": "Find literature on moisture-induced degradation and defect passivation of halide perovskite solar cells.",
 "query_terms": [
  "cells",
  "defect",
  "degradation",
  "halide",
  "moisture-induced",
  "passivation",
  "perovskite",
  "solar"
 ],
 "snapshots_seen": 5,
 "snapshots_verified": 2,
 "snapshots_quarantined": 3,
 "records_verified": 5,
 "unique_records": 4,
 "ranked_candidates": 4,
 "zero_hit_terms": [],
 "year_window": [
  2019,
  null
 ]
}
```

## Interpretation

- Quarantined snapshots never entered the corpus; see quarantine_report.md.
- `zero_hit_terms` lists query concepts with no match in the verified corpus — an honest coverage gap, to be copied into result.json uncertainty.
- Every candidate carries provenance {file, json_index, sha256_12}; a reviewer can re-open the exact snapshot and record.
