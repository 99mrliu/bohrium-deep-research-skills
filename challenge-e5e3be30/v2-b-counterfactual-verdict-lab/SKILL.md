---
name: counterfactual-verdict-lab
description: Calibrate four-level scientific claim verdicts with independently adjudicated minimal-pair/counterfactual probes. Use when negation, comparison direction, statistical significance, causation versus correlation, quantifiers, or condition scope must be checked for expected verdict invariance or flips; includes source re-review, transition reports, bounded probe sampling, and dynamic output-contract handling.
---

# Counterfactual Verdict Lab

## Unique purpose and non-goals

Use the original claims and a **small, prioritized set of one-operator probes** as calibration experiments. Independently read and adjudicate the original claim and each selected probe against the complete source context. Only then compare the observed `original_verdict -> probe_verdict` transition with the evidence-aware `expected_relation`.

This is not claim splitting, a rule-ledger verdict service, dual-channel kappa scoring, or quote auditing. The scripts never infer a scientific verdict from wording, an operator, or an expected relation. They validate the probe design, compare already independent annotations, and expose transitions requiring source re-review.

The four verdicts are exactly `supported`, `partially_supported`, `contradicted`, and `insufficient_evidence`; see `references/confidence_levels.md`. Topic overlap is not support. Non-reporting is not disproof. Preserve every material source conflict rather than averaging it away.

## Runtime contract

The evaluator installs this directory at `/skills/weekly-skill`. Use only relative Skill resources and the runtime locations below; no network access is required.

1. Read `/input/case.json`, `/input/task.md`, `/input/claims-to-verify.json`, and the actual supplied paper files. Claims are questions to test, never authoritative facts.
2. Create `/app/work` and `/app/output`. Immediately create an honest partial result from the case's actual `output_contract` and continue improving it:

```bash
python3 /skills/weekly-skill/scripts/contract_tools.py skeleton \
  --case-json /input/case.json \
  --output /app/output/result.json
```

The skeleton handles list- and dictionary-shaped contracts. Inspect and populate **every** original output-contract field. The final result also requires matching `case_id`, `status`, `sources`, `uncertainty`, and `change_records`. A partial result must state what is missing and where manual review can resume.

3. Read the entire relevant source context, not merely retrieved snippets. For PDFs use the available PDF text/render/OCR tools; record page, section, paragraph, figure/table, or field locators. Do not assume source content from filenames or labels.
4. Independently annotate every original claim before probe comparison. Then create candidate probes, select a bounded set, and independently annotate each selected probe without deriving its verdict from the original verdict or expectation. Use `references/probe_protocol.md` for annotation and JSON formats.
5. Budget conservatively: default to at most 12 selected probes and no more than two per original claim, with at most two candidates per operator per claim. Reserve at least 10 of the 64 model requests for re-review and finalization. Save source annotations and partial outputs incrementally within the 900-second run.

Select by pre-verdict risk, not by a desired outcome:

```bash
python3 /skills/weekly-skill/scripts/probe_ops.py select \
  --plan /app/work/probe-candidates.json \
  --output /app/work/probe-plan.json \
  --max-probes 12 --seed 17
```

6. Check one-operator construction and observed verdict transitions:

```bash
python3 /skills/weekly-skill/scripts/transition_check.py \
  --claims /input/claims-to-verify.json \
  --probe-plan /app/work/probe-plan.json \
  --annotations /app/work/independent-annotations.json \
  --sources /app/work/sources.json \
  --report /app/work/transition-report.json
```

Exit `0` means all selected transitions are consistent. Exit `1` means malformed input or an illegal zero-/multi-operator edit; report it honestly and repair the design. Exit `2` means a semantic calibration inconsistency, **not permission to auto-change a verdict**.

7. On exit `2`, return to the original paper and re-read both claims with their full conditions, direction, quantifiers, and study design. Record old and new annotations, source locators, review rationale, reviewer stage, and unresolved disagreements in `change_records`. Revise a verdict only when the source re-review warrants it; alternatively correct a mistaken probe plan or expected relation with a documented reason. Re-run the checker. Never edit an annotation merely to force exit `0`.
8. Populate the actual contract fields, include both original and probe verdicts or a compact transition summary as appropriate, list sources and conflicts, and validate:

```bash
python3 /skills/weekly-skill/scripts/contract_tools.py validate-final \
  --case-json /input/case.json \
  --result /app/output/result.json
```

Set `status` to `success` only when required reading and reviews are complete. Use `partial` for unresolved inconsistencies, unreadable/missing materials, unfinished probes, or incomplete required fields; explain limits in `uncertainty`. Use `failed` only when no substantive verification was possible. Keep all conflicts and both source locations in the result.

Generate a text SVG directly from the actual transition report when a visual preview is useful or requested:

```bash
python3 /skills/weekly-skill/scripts/render_transition_svg.py \
  --report /app/work/transition-report.json \
  --output /app/output/transition-preview.svg
```

## Probe discipline

Each candidate must declare its single operator, before/after semantic signatures, an exact one-span text edit, semantic strength relation (`same`, `weaken`, or `strengthen`), and evidence-aware expected transition relation (`same`, `weaken`, `strengthen`, `flip_to_contradicted`, or `become_insufficient`). The signatures cover all six operators so that even one continuous sentence replacement cannot hide a second semantic change. Independent annotation signatures must agree with the plan. The checker uses these structures only for design/transition consistency, never as scientific truth. See `references/verdict_operations.md` for boundaries.

A failed expectation is a trigger to revisit the evidence. It is not an automatic contradiction, support upgrade, or downgrade.

## Minimal complete synthetic example

All files under `examples/synthetic` and all generated demonstration outputs are **SYNTHETIC**, not real scientific evidence or benchmark scores. The example covers all six operators, selects 6 of 8 candidates using pre-verdict risk, finds one causality-probe inconsistency in the independent initial annotations, records source re-review, corrects it, and then passes.

```bash
python3 /skills/weekly-skill/scripts/run_synthetic_demo.py \
  --work-dir /app/work/synthetic-demo \
  --output-dir /app/output/synthetic-demo
python3 /skills/weekly-skill/scripts/selftest.py
python3 /skills/weekly-skill/scripts/validate_bundle.py
```

The demo writes initial and revised transition reports, before/after annotations, change/review records, a dynamically populated `result.json`, and an SVG rendered from the final observed transition data. `selftest.py` also runs the illegal multi-point perturbation and requires exit `1`.

## Limits

The semantic signatures and verdict annotations require source-grounded Agent judgment; the standard-library scripts cannot replace scientific reading. The transition checker does not establish external reproducibility, resolve genuine source disagreement, or prove that a selected probe set is exhaustive. Long documents, OCR errors, inaccessible evidence, and unchecked claims remain explicit uncertainty items.
