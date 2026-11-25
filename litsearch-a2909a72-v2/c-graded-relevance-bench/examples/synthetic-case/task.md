# Task — SYNTH-C-001 (SYNTHETIC fixture, not a formal case)

The candidate pool is fixed: the organizer-local snapshot under
`snapshots/` (a Crossref-shaped JSON page; no live remote coverage exists).

1. Grade every unique record in the pool against the research question on a
   0-3 graded relevance scale, with a per-facet decomposition a reviewer can
   verify point by point.
2. Rank the pool by graded relevance and report ranking-quality statistics
   (grade histogram, confidence tiers, honest coverage gaps).
3. Route borderline records into an explicit adjudication queue, then apply
   the adjudicator's final grades and report engine-vs-adjudication
   agreement (nDCG@10, self-consistency only).
4. Deliver `result.json` with the original `case_id` and every field named
   by `output_contract` in `case.json`.

Deliverables under the output directory: `graded_candidates.json` /
`graded_candidates.md`, `borderline_queue.json`, `ranking_report.md`,
`adjudication_ledger.md` (once adjudicated), `evidence/evidence_index.json`,
and `result.json`.
