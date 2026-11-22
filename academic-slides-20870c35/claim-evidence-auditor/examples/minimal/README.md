# Minimal invocation example (illustrative, synthetic)

Interface demonstration only; the paper, numbers and outputs are **synthetic**, not a formal case result.

## Input (hypothetical)

- `/input/case.json` — `case_id: "DEMO-SYNTH"`, output contract root fields `case_id, status, editable_source, export_artifact, content_map, compliance_checks, exceptions`.
- `/input/paper.pdf` — hypothetical paper; Figure 2 reports error 22.0 vs 25.0 baseline.
- `/input/artifacts/slide-workorder.json` — 8 slides, defense committee, template supplied, full-source rule: every figure dispositioned.

## Invocation

> Use claim-evidence-auditor on the paper and work order under /input; deliver the deck, content map, coverage ledger, audit report and result.json to /app/output.

## What the agent does

1. Contract intake; early `result.json` (`partial`).
2. `python3 scripts/pdf_index.py /input/paper.pdf --out /app/work/source_index.json` → registry of 6 exhibits over 12 pages (illustrative).
3. Claim cards (`claims.example.json` here shows the format): each with locator, anchor quote, strength grade.
4. Page plan binding claim IDs per slide; `coverage.json` dispositions all 6 exhibits (5 on slides, 1 omitted with reason).
5. Deck built on the template; Figure 2 cropped from the rendered source page, cited "Figure 2, p.4".
6. Audit:
   `python3 scripts/audit_deck.py /app/output/presentation.pptx --index /app/work/source_index.json --claims /app/work/claims.json --coverage /app/output/coverage.json --out /app/output/audit_report.json`
   → number/citation/strength/coverage gates; then the visual gate compares each crop with the rendered source page.
7. `result.json` finalized: real paths, observed compliance values, any open findings echoed under exceptions.

## Illustrative artifact

`claims.example.json` — two claim cards in delivery format. Marked as an example; reuse the format, never the content.
