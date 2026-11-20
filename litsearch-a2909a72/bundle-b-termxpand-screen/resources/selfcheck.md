# Final self-check (run through before finalizing result.json)

1. `result.json` exists, carries the original `case_id`, and every `output_contract`
   field is present and non-empty (`make_result.py --validate` passes).
2. `status` honest: `success` only with no source failures and no zero-coverage
   concepts; otherwise `partial` with substance in `uncertainty`.
3. Counts in `prisma_flow.md` are internally consistent: identified = included + all
   exclusion codes; the ledger row count matches.
4. `screening_ledger.csv` has a decision + reason code for every record, and included
   rows carry an evidence snippet; spot-check 3 rows against the snippet text.
5. Top-10 rows of `candidates.md` are on-topic; if not, terms were fixed and the
   engine re-run (outputs never hand-edited).
6. `expansion_report.md` shows each concept's expanded term set — abbreviations and
   zh/en equivalents are inside concepts, not split into separate concepts.
7. `omissions.md` zero-coverage concepts (if any) are copied into `uncertainty`.
8. Every candidate traces to a real source: `provenance` entries name source + query;
   `evidence/search_log.jsonl` has one line per executed query with real URLs.
9. Threshold choice (if changed from 0.35) is stated in the report/result.
10. Budget respected (~≤12 model requests); no hand-issued duplicate API queries
    outside the engine.
