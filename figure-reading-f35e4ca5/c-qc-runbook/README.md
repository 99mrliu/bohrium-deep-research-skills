# qc-gated-figure-reading

Skill for challenge **阅读02｜科研图表解析** (challenge-f35e4ca5).
Center: **process quality control** — a budget-gated runbook:
result-first skeleton at minute zero, then five machine-checked gates
(inventory, axis card, element coverage ledger, crosscheck, output lint)
with exit codes; finalize computes the shipped status from gate evidence
and emits run_report.md. Method-agnostic: any extraction method passes
through the same gates.

- `SKILL.md` — the runbook (runtime contract, gates, failure catalogue)
- `scripts/start_run.py` — gate 0: run state + valid partial result.json (stdlib)
- `scripts/gate.py` — gates g1–g5 with hard rules (stdlib)
- `scripts/finalize.py` — status decided from gates + run_report.md (stdlib)
- `references/` — gate definitions/timeboxes, axis-card and element-ledger formats
- `examples/` — runnable synthetic miniature incl. fail-mode demo (marked as example)

Run the example: `python examples/make_synthetic_case.py`
