# Minimal example (SYNTHETIC — 合成示例, not a formal test case)

Synthetic input only: a 3-page artificial paper PDF plus a 6-field
synthetic `target-fields.json`. All outputs below are 示例 from the
synthetic run.

## Commands and observed behaviour (示例)

```bash
python3 scripts/build_bank.py --pdf synth_paper.pdf --work-dir /app/work
# -> layer -> 31 sentences; bank -> 18 entries

# (bind fields into /app/output/result.json — semantic work)

python3 scripts/verify.py --result /app/output/result.json --work-dir /app/work
# -> verify: PASS (22 checks, 0 errors)

python3 scripts/render_audit.py --result /app/output/result.json \
    --work-dir /app/work --out /app/output/audit_report.html \
    --pdf synth_paper.pdf --pages-dir /app/output/pages
# -> audit -> audit_report.html (6 fields, 3 previews)
```

## Tamper detection observed in the synthetic run (示例)

Three deliberate corruptions were introduced into a copy of the result —
a paraphrased quote, a wrong page number, a dangling `bank_id` — and the
join-check failed loudly on exactly those records:

```text
ERROR [J2 capacity_composite_100cyc] quote verbatim in layer
ERROR [J3 capacity_composite_100cyc] quote on stated page 1
ERROR [J4 retention_composite_100cyc] bank_id B9999 resolves, quote equal
ERROR [J3 ice_first_cycle] quote on stated page 3
verify: FAIL (23 checks, 4 errors)   exit=1
```

## Rendered artifacts (示例)

- `audit_report.html` — self-contained HTML: coverage matrix, six evidence
  cards with the scalar highlighted inside its quote, claims grouped by
  kind (conclusion/limitation/speculation), uncertainty table for the two
  synthetic `not_reported` fields, J1–J5 check table.
- `pages/page-1-1.png … page-3-3.png` — rendered page previews of the
  synthetic PDF for visual spot-checking.
