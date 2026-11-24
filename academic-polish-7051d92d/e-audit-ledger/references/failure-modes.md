# Failure modes — observed failures, the gate that catches them, and recovery

| # | failure mode | symptom | gate | recovery |
|---|---|---|---|---|
| F1 | Edit claims to fix sXXXX but its `original` differs from the frozen sentence (whitespace drift, model retyped it) | intake rejection "anchor mismatch" | C02 | Copy `original` verbatim from `intake-report.json` / `state.json`; never retype |
| F2 | Vacuous reason ("improve fluency", "提升流畅性", "polish") | intake rejection "vacuous reason blacklisted" | C07 | Name the defect and the rule; if you cannot, drop the edit |
| F3 | Reason shorter than 12 characters | intake rejection "reason too short" | C07 | Same as F2 — a real defect takes a sentence to describe |
| F4 | Number/unit, %, p-value, citation or figure pointer lost or altered in `revised` | intake rejection / apply-time rollback "protected token" | C03 | Restore the token verbatim; if the notation is unusual, check it manually and note it in `uncertainty` |
| F5 | New number/unit invented by the edit | "protected token(s) introduced" | C03 | Remove the invention; polishing never adds data |
| F6 | Edit accepted but never reviewed (batch was big, reviewer skipped "obvious" ones) | `rolled_back_unreviewed` in review report | C04 | Add the missing review record and re-run `review` — the rollback is a safety net, not a dead end |
| F7 | Batch edited after review → hash mismatch | `rolled_back_stale` | C04 | Re-review the changed edit; staleness is by design |
| F8 | One edit batch file is corrupt JSON | batch marked `corrupt`, others still processed | intake merge policy | Fix or delete the bad file and re-run intake; keep batches ≤15 sentences so loss is small |
| F9 | Sentence merged/split/reordered by an over-eager edit | export aborts: "polished text does not equal sentence-by-sentence refill" | C01 | Edits must be within-sentence; re-cut the offending edit |
| F10 | Hand-written result.json drifts from the case contract | validate-result failures (missing field, wrong type, case_id mismatch) | contract mirror | Always `result-skeleton` from the real case.json, fill, then `validate-result` |
| F11 | Contract field with nothing real to map filled with invented content | silent lie | honesty rule | Write `null` + `notes` entry (honest null); see `output-contract.md` |
| F12 | "Gates all pass, so the polish must be good" | over-claim in delivery | — | Gates prove "没改坏" only. Do the final read-through; machine checks cannot prove "改得漂亮" |
| F13 | Re-run produces different bytes (timestamp/random leaked into output) | determinism diff non-empty | run.sh diff step | All scripts are timestamp- and random-free; find and remove the leak before delivering |
| F14 | Review records with decision "ok" / missing reason | listed under `invalid_review_records`, edits roll back | C04 | A review reason must be concrete, ≥8 chars; redo the record |
