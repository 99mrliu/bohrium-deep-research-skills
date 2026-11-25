# Minimal invocation example — SYNTHETIC, not a formal case result

The outputs below were produced by **actually running this exact skill
version** on the synthetic fixture in `examples/synthetic-case/` (all records
fictional, DOIs under the reserved `10.0000` prefix). They demonstrate the
two-stage engine-plus-adjudication interface end-to-end; they are **not**
results of any organizer test case. The real artifacts are kept under
`examples/synthetic-output/` (stage 1 in its `stage1-engine/` subdir) so a
reviewer can diff them against a fresh run.

## Input

`examples/synthetic-case/case.json` (excerpt):

```json
{"case_id": "SYNTH-C-001",
 "research_question": "Which publications report defect passivation strategies that improve the moisture stability of halide perovskite solar cells?",
 "output_contract": {"graded_candidates": "...", "borderline_queue": "...", "ranking_report": "...", "evidence_manifest": "..."}}
```

`examples/synthetic-case/facets.json` ships three agent-authored facets
(material / problem / method) with synonyms; `snapshots/crossref_page1.json`
ships five Crossref-shaped fictional records designed to exercise every grade:

| record | design intent | expected engine grade |
|-|-|-|
| `10.0000/synth.c.001` | all 3 facets hit in the title | 3 (clear-include) |
| `10.0000/synth.c.002` | 2 of 3 facets hit in the title | 2 (clear-include) |
| `10.0000/synth.c.003` | single abstract-only mention of one facet term | 1 (borderline → queue) |
| `10.0000/synth.c.004` | unrelated topic (methane reforming catalysis) | 0 (clear-exclude) |
| `10.0000/synth.c.001` (again) | duplicate DOI of the first record | merged by dedup |

## Invocation (exactly what was run, from the bundle root)

```
# stage 0: secure a partial result
python3 scripts/make_result.py --case examples/synthetic-case/case.json \
    --out examples/synthetic-output/result.json --status partial \
    --uncertainty "borderline adjudication still open (stage 1 of 2)"

# stage 1: engine grading run (kept in its own subdir)
python3 scripts/grade_relevance.py --case examples/synthetic-case/case.json \
    --input examples/synthetic-case --work examples/synthetic-case \
    --out examples/synthetic-output/stage1-engine

# stage 2: apply the adjudications (file kept in synthetic-output for transparency)
python3 scripts/grade_relevance.py --case examples/synthetic-case/case.json \
    --input examples/synthetic-case --work examples/synthetic-case \
    --out examples/synthetic-output \
    --adjudicate examples/synthetic-output/adjudications.json

# finalize + validate
python3 scripts/make_result.py --case examples/synthetic-case/case.json \
    --out examples/synthetic-output/result.json --status success --clear-uncertainty
python3 scripts/make_result.py --case examples/synthetic-case/case.json \
    --out examples/synthetic-output/result.json --validate
```

## Actual engine digests (stdout of the kept runs)

Stage 1 (engine only — note the grade-1 borderline record and the merged
duplicate):

```json
{"ENGINE_STATUS": "success", "question": "Which publications report defect passivation strategies that improve the moisture stability of halide perovskite solar cells?", "facets_source": "agent-file:examples/synthetic-case/facets.json", "n_facets": 3, "facets": [{"name": "material", "terms": ["halide perovskite", "perovskite", "perovskite solar cell"]}, {"name": "problem", "terms": ["humidity", "moisture", "stability", "water-induced degradation"]}, {"name": "method", "terms": ["defect healing", "defect passivation", "passivation", "surface treatment"]}], "files_consulted": 1, "files_skipped": 0, "records_loaded": 5, "unique_records": 4, "duplicates_merged": 1, "grade_histogram": {"3": 1, "2": 1, "1": 1, "0": 1}, "tiers": {"clear-include": 2, "borderline": 1, "clear-exclude": 1}, "borderline_count": 1, "zero_hit_facets": [], "findings": []}
```

Stage 2 (after `adjudications.json` promoted `10.0000/synth.c.003` from engine
grade 1 to final grade 2 with a rationale — histogram shifts, queue drains,
nDCG@10 self-consistency reported):

```json
{"ENGINE_STATUS": "success", "question": "Which publications report defect passivation strategies that improve the moisture stability of halide perovskite solar cells?", "facets_source": "agent-file:examples/synthetic-case/facets.json", "n_facets": 3, "facets": [{"name": "material", "terms": ["halide perovskite", "perovskite", "perovskite solar cell"]}, {"name": "problem", "terms": ["humidity", "moisture", "stability", "water-induced degradation"]}, {"name": "method", "terms": ["defect healing", "defect passivation", "passivation", "surface treatment"]}], "files_consulted": 1, "files_skipped": 0, "records_loaded": 5, "unique_records": 4, "duplicates_merged": 1, "grade_histogram": {"3": 1, "2": 2, "1": 0, "0": 1}, "tiers": {"clear-include": 2, "borderline": 1, "clear-exclude": 1}, "borderline_count": 0, "zero_hit_facets": [], "findings": [], "adjudications_applied": 1, "grades_changed": 1, "borderline_resolved_by_adjudication": 1, "ndcg_at_10_engine_vs_adjudication": 1.0}
```

Validator output:

```
CHECK PASS: 4 contract fields filled, case_id=SYNTH-C-001, status=success
```

## What the run demonstrates

- **Grades exactly as designed**: 3 / 2 / 1 / 0 histogram in stage 1; every
  grade in `graded_candidates.md` carries per-facet matched terms, hit fields,
  contribution weights and evidence snippets (see record 3's `weak` method
  facet with the abstract sentence as evidence).
- **Dedup**: 5 loaded records → 4 unique; the duplicate of
  `10.0000/synth.c.001` is merged and visible under `also_in`.
- **Borderline queue**: stage 1 routes exactly record `synth.c.003` into
  `stage1-engine/borderline_queue.json` with the concrete question "Does the
  term 'passivation' appearing only in the abstract satisfy facet 'method'
  for the research question: ...?".
- **Adjudication ledger, never silent**: stage 2 applies the agent's override
  (1 → 2), records it in `adjudication_ledger.md` with rationale, drains the
  queue (`borderline_count: 0`, `borderline_resolved_by_adjudication: 1`), and
  reports **nDCG@10 = 1.0 as engine-vs-adjudication agreement** — the engine
  ranking needed no reordering against the adjudicated grades. This is a
  self-consistency number, not a benchmark score.
- **Contract**: `result.json` validates with all 4 output_contract fields
  mapped to real artifacts and hashed sources.

## Output files (real, regenerated by the commands above)

- `synthetic-output/stage1-engine/` — the pure engine run: `graded_candidates.json/.md`,
  `borderline_queue.json` (1 record), `ranking_report.md`, `evidence/`
- `synthetic-output/graded_candidates.json` / `.md` — final ranked records with
  full decomposition and adjudication annotations
- `synthetic-output/borderline_queue.json` — drained (count 0) after adjudication
- `synthetic-output/adjudications.json` — the adjudicator's overrides + rationale (kept for transparency)
- `synthetic-output/adjudication_ledger.md` — engine grade vs final grade
- `synthetic-output/ranking_report.md` — digest + interpretation
- `synthetic-output/evidence/evidence_index.json` — sha256 manifest (case, snapshot, adjudications)
- `synthetic-output/result.json` — contract-filled, validated, `status=success`
