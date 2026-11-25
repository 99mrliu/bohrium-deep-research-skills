# Minimal invocation example — SYNTHETIC, not a formal case result

Everything below was produced by **actually running this exact skill version**
on the synthetic fixture in `examples/synthetic-case/` (all records fictional,
DOIs under the reserved `10.0000` prefix). Two demonstrations are kept under
`examples/synthetic-output/` so a reviewer can diff them against a fresh run:

- `synthetic-output/clean/` — a normal run that passes the warden
  (**GATE: PASS**, exit 0);
- `synthetic-output/tampered/` — the same run with one phantom candidate
  injected by hand, caught by the warden (**GATE: FAIL**, exit 1);
- `synthetic-output/result.json` + `audit_report.md|json` (top level) —
  copies of the clean run's final deliverables.

## Input

`examples/synthetic-case/case.json` (excerpt):

```json
{"case_id": "SYNTH-E-001",
 "research_question": "Find literature on CRISPR gene drive systems for malaria vector control in Anopheles mosquitoes.",
 "output_contract": {"candidate_literature": "...", "retrieval_run_log": "...",
                     "warden_audit": "...", "status_report": "..."}}
```

`examples/synthetic-case/snapshots/crossref_page1.json` ships 4 fictional
Crossref-shaped records on purpose:

| record | role |
|-|-|
| `10.0000/synth.e.001` (published) | on-topic: CRISPR gene drive vs Anopheles |
| `10.0000/synth.e.002` | on-topic: CRISPR editing of malaria parasite loci |
| `10.0000/synth.e.003` | off-topic: alpine soil microbiome (score 0) |
| `10.0000/synth.e.001` (preprint) | duplicate DOI → must dedup |

## Demonstration (a): clean run

Exactly what was run:

```
python3 scripts/make_result.py --case examples/synthetic-case/case.json \
    --out examples/synthetic-output/clean/result.json --status partial \
    --uncertainty "run not started yet"
python3 scripts/lite_search.py --case examples/synthetic-case/case.json \
    --input examples/synthetic-case \
    --work examples/synthetic-output/clean --out examples/synthetic-output/clean
python3 scripts/warden.py --case examples/synthetic-case/case.json \
    --run examples/synthetic-output/clean/run --out examples/synthetic-output/clean
python3 scripts/make_result.py --case examples/synthetic-case/case.json \
    --out examples/synthetic-output/clean/result.json --status partial \
    --uncertainty "...gaps..."   # then warden again, then --validate
```

Actual lite_search digest (stdout):

```json
{"ENGINE_STATUS": "ok", "snapshots": 1, "identified": 4, "after_dedup": 3, "included": 2, "zero_hit_terms": ["mosquitoes", "systems"], "run_dir": ".../examples/synthetic-output/clean/run"}
```

The PRISMA flow in `clean/run/run_log.jsonl` (step → counts):

```
discover {'out': 1}  →  evidence_copy 1→1  →  ingest 1→4  →  dedup 4→3
→  score 3→2  →  exclusions 2  →  prisma {identified: 4, after_dedup: 3,
   scored: 2, included: 2}  →  finalize 2
```

(4 identified → 3 after the preprint duplicates `synth.e.001` → 2 included;
the soil-microbiome record is excluded with reason `NO_TERM_MATCH`.)

First warden pass ran while `result.json` still had empty contract fields —
exit 1, 4 `CONTRACT_FIELD_EMPTY` errors, exactly as designed. After filling
the contract with `make_result.py`, the final audit:

```json
{"GATE": "PASS", "errors": 0, "warnings": 2, "gate_status": {"ANTI-FABRICATION": "PASS", "FLOW": "PASS", "CONTRACT": "PASS", "ANOMALY": "PASS"}, "audit_report": "examples/synthetic-output/clean/audit_report.md"}
```

**warden exit code: 0.** The 2 WARNs are honest anomalies, copied into
`result.json`'s `uncertainty`: `ZERO_HIT_TERMS` (`mosquitoes`, `systems`
matched no record) and `SINGLE_SOURCE_POOL` (one snapshot, one source type).

Final validation:

```
VALIDATE OK: 4 contract fields, case_id=SYNTH-E-001, status=partial
```

**validate exit code: 0.** Status stays `partial` because coverage gaps are
real and ledgered — the honest outcome for a one-snapshot synthetic pool.

## Demonstration (b): tampered run — phantom DOI caught

`tampered/run/` is a copy of the clean run with one hand-injected candidate in
`candidates.json`: rank 3, DOI `10.0000/synth.e.phantom`, title "Phantom field
trial of CRISPR gene drive eliminating malaria vectors entirely", pointing at
a real evidence file it does not appear in. The warden audit:

```json
{"GATE": "FAIL", "errors": 4, "warnings": 2, "gate_status": {"ANTI-FABRICATION": "FAIL", "FLOW": "FAIL", "CONTRACT": "FAIL", "ANOMALY": "PASS"}}
```

**warden exit code: 1.** The findings (see `tampered/audit_report.md`,
re-checkable by hand with the grep commands in each finding):

- `[ERROR] ANTI-FABRICATION — FABRICATION_SUSPECT`: DOI
  `10.0000/synth.e.phantom` claimed by candidates.json rank=3 appears in NO
  evidence copy;
- `[ERROR] ANTI-FABRICATION — FABRICATION_SUSPECT`: the phantom title appears
  in NO evidence copy;
- `[ERROR] FLOW — COUNT_MISMATCH`: run_log reports `included=2` but
  independent recomputation gives 3 (the hand edit broke the ledger);
- `[ERROR] CONTRACT — RESULT_MISSING` on the first pass (no result.json yet).

Then `warden.py --fix-result` (exit 1 — repair does not launder): it wrote
`tampered/result.json` with `status=partial` and every ERROR/WARN finding
listed in `uncertainty`, staging copies of `candidates.md` and
`run_log.jsonl` into the output dir — **without touching the tampered
candidates**. The `RESULT_MISSING` note inside `uncertainty` is truthful: it
records that no result.json existed at fix time. Re-audit after the repair:

```json
{"GATE": "FAIL", "errors": 3, "warnings": 2, "gate_status": {"ANTI-FABRICATION": "FAIL", "FLOW": "FAIL", "CONTRACT": "PASS", "ANOMALY": "PASS"}}
```

**exit code: 1** — the contract gate now passes, but the fabrication findings
survive, by design. This FAIL report is the honest deliverable for a tampered
run.

## Output files (real, regenerated by the commands above)

- `synthetic-output/clean/run/` — candidates.json/md, run_log.jsonl,
  `evidence/faad68f10bc0__crossref_page1.json` (byte-identical snapshot copy)
- `synthetic-output/clean/audit_report.md|json` — final PASS audit
- `synthetic-output/clean/result.json` — contract-filled, validated, partial
- `synthetic-output/tampered/run/` — same layout with the phantom candidate
- `synthetic-output/tampered/audit_report.md|json` — FAIL audit naming the
  phantom DOI
- `synthetic-output/tampered/result.json` — `--fix-result` honest partial
- `synthetic-output/result.json`, `audit_report.md|json` — top-level copies
  of the clean deliverables
