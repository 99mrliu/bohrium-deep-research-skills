# Pre-submission checklist — graded-relevance-bench

Run through this before delivering `result.json`. Every "no" is either a fix
or an `uncertainty` note — never silence.

## Contract

- [ ] `result.json` exists under `/app/output` and carries the **original**
      `case_id` from `/input/case.json`.
- [ ] Every field named by `output_contract` is filled and points to a real,
      existing file (the validator checks this — run it).
- [ ] Final
      `make_result.py --case /input/case.json --out /app/output/result.json --validate`
      prints `CHECK PASS`.
- [ ] `status` is honest: `partial` whenever a borderline queue stands
      unadjudicated, a facet has zero hits, or any snapshot was skipped.
- [ ] `status=success` only with empty `uncertainty` (validator enforces).

## Grading integrity

- [ ] `facets.json` was authored with synonyms (or the fallback note appears
      in `ranking_report.md` and is acknowledged in `uncertainty`).
- [ ] The grade histogram in the digest is plausible (all-zero or all-three
      histograms mean the facets are wrong — fix facets, not outputs).
- [ ] Spot-checked at least the top 5 rows of `graded_candidates.md`: each
      contribution point is backed by its evidence snippet.
- [ ] `zero_hit_facets` from the digest are either resolved (richer terms /
      wider corpus, one re-run) or listed in `uncertainty`.
- [ ] `files_skipped` in `ranking_report.md` is empty, or every entry's
      reason is understood and acceptable.

## Adjudication

- [ ] Every record in `borderline_queue.json` was either adjudicated via
      `--adjudicate` or explicitly reported as unadjudicated in
      `uncertainty`.
- [ ] Each adjudication has a rationale; `adjudication_ledger.md` shows
      engine grade vs final grade for all of them.
- [ ] The nDCG@10 in the digest/ledger is reported as
      **engine-vs-adjudication agreement**, never as a benchmark score.
- [ ] No output file was hand-edited; all changes went through facets.json or
      adjudications.json + a re-run.

## Traceability

- [ ] `evidence/evidence_index.json` lists every consulted file (case,
      snapshots, facets, adjudications) with sha256.
- [ ] Every record in `graded_candidates.json` carries provenance
      (`file`, `json_index`, `sha256_12`) and merged duplicates show up in
      `also_in`.
- [ ] One-line engine digest was captured (stdout) and matches the digest
      embedded in `ranking_report.md`.
