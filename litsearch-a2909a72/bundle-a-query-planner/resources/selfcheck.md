# Final self-check (run through before finalizing result.json)

1. `result.json` exists at `/app/output/result.json`, contains the case's original
   `case_id` verbatim, and every field named in the case's `output_contract` is present
   and non-empty (run `make_result.py --validate`).
2. `status` is honest: `success` only when no source failures and no uncovered facets;
   otherwise `partial` with the substance in `uncertainty`.
3. `candidates.md` top-10 titles were eye-balled and are on-topic for the research
   question; if not, the plan was fixed and the engine re-run (not the output edited).
4. Every candidate in `candidates.json` has at least one `provenance` entry with a real
   `source` and `query`; spot-check one `raw` file under `evidence/raw/` opens and
   contains the record.
5. `search_report.md` shows the stop reason and per-facet coverage; any **NOT COVERED**
   facet is copied into `uncertainty`.
6. `evidence/search_log.jsonl` contains at least one line per executed query with real
   URLs; queries with `ok: false` appear in the report's failure list.
7. No paper in the output was written by hand; metadata gaps are `null`, not guesses.
8. Local snapshots under `/input` were ingested (round 0 line in the log) or their
   absence/skip is explained.
9. `sources` in `result.json` lists the input files actually consulted (the builder
   fills this automatically — do not trim it).
10. Total model requests stayed within budget (~≤12); no repeated identical queries
    were issued outside the engine.
