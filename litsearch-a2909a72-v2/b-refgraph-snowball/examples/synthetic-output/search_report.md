# Search report (refgraph-snowball)

```json
{
 "ENGINE_STATUS": "success",
 "question": "Map the citation neighbourhood around the seed study on humidity-controlled crystallization of perovskite films: stability, moisture and passivation work.",
 "query_terms": [
  "citation",
  "crystallization",
  "films",
  "humidity-controlled",
  "moisture",
  "neighbourhood",
  "passivation",
  "perovskite",
  "seed",
  "stability"
 ],
 "snapshots_seen": 3,
 "reference_files_seen": 0,
 "records_loaded": 6,
 "unique_records": 6,
 "seed_origin": "explicit-case",
 "seeds_matched": [
  {
   "key": "doi:10.0000/synth.b.s01",
   "doi": "10.0000/synth.b.s01",
   "title": "Solvent-free crystallization of perovskite films under controlled humidity"
  }
 ],
 "seeds_unmatched": [],
 "references_extracted": 7,
 "references_resolved": 5,
 "references_unresolved": 2,
 "unresolved_by_reason": {
  "doi-not-in-corpus": 1,
  "no-identifier": 1
 },
 "graph_edges": 5,
 "graph_density": 0.1667,
 "candidates": 5,
 "seeds_without_resolvable_refs": [],
 "max_hops": 2
}
```

## Interpretation

- Recall comes from GRAPH TRAVERSAL over the retained reference lists, not from query planning: backward = references of seeds that resolve locally; forward = local records whose reference lists cite a seed.
- `score_breakdown` shows every component of each candidate's score; the formula is in references/methodology.md.
- Unresolved references are ledgered in unresolved_references.md with reason codes — they are findings about corpus coverage.
- Records not reachable within 2 hop(s) remain in graph.json but are excluded from candidates.

## Honest gaps

- 2 reference(s) unresolved (doi-not-in-corpus=1, no-identifier=1) — genuine coverage gaps of the local corpus.
