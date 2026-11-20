# Final self-check (run through before finalizing result.json)

1. `result.json` exists, carries the original `case_id`, and every `output_contract`
   field is present and non-empty (`make_result.py --validate` passes).
2. `status` honest: `success` only when every source is `ok`/`empty` in
   `source_status.md`; otherwise `partial` with degraded sources named in
   `uncertainty`.
3. Arithmetic holds in `dedup_report.md`: raw hits = canonical records + merged-away
   sightings; per-source input counts match `fetch_log.jsonl`.
4. Spot-check one canonical record in `final_records.json`: its `provenance` entries
   name real sources/queries, and the referenced `raw` cache file exists under
   `evidence/raw/`.
5. Metadata conflicts (if any) are listed with both values and both sources; none was
   resolved silently.
6. DOI verification tally (verified / metadata-mismatch / unreachable / not-checked)
   matches `dedup_report.md`; no `not-checked` record is described as verified anywhere.
7. `candidates.md` top-10 are on-topic; multi-source records appear before
   single-source ones.
8. Local snapshots under `/input` appear in the pool (local-snapshot source line in
   `source_status.md`) or their absence is explained.
9. No output file was hand-edited after the scripts ran; any needed change was made
   through `queries.json` or script flags followed by a re-run.
10. Budget respected (~≤12 model requests); no manual duplicate API calls outside the
    scripts.
