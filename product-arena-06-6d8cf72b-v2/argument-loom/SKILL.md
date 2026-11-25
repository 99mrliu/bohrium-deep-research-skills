---
name: argument-loom
description: Build and audit section-native scientific argument graphs from paper PDFs, preserving claims, evidence, warrants, transitions, and limitations for source-grounded literature notes and QA.
---

# Argument Loom

## When to use / not use

Trigger this skill for requests such as “read these PDFs and make section-by-section argument notes,” “map each claim to its evidence and reasoning,” “compare limitations across Results and Discussion,” or “answer paper QA with auditable section anchors.” It is useful when a literature review must preserve the rhetorical role of Abstract, Introduction, Methods, Results, Discussion, and Conclusion rather than flatten a paper into generic cards.

A useful non-trigger is a bibliography-only citation formatter with no need to read paper content. Do not use this as a PDF text-extraction fidelity benchmark, a generic paper-card generator, or a schema-validation-only exercise.

## Platform runtime and budget

Read the **actual** `/input/case.json`, `/input/task.md`, and every supplied paper. Work only in `/app/work`; write deliverables to `/app/output`. Use platform-provided `pdftotext` (normally with `-layout`) for a first reading, `pdftoppm` for relevant page images, and platform OCR when a page is scanned. Inspect figures/tables when they carry evidence. Never use personal paths, network retrieval, prepared official answers, or unstated prior paper knowledge.

`result.json` must contain the case's `case_id` and every declared top-level `output_contract` property needed by the task, with exactly the contracted names and nested types; do not treat properties outside `required` as permission to omit a declared deliverable. If `additionalProperties` is false, put provenance, status, uncertainty, or change history in contract fields when allowed; otherwise use separate auxiliary artifacts. Never add a convenient extra key to `result.json`. Use `assemble --response response.json` to supply contract-specific direct answers or other declared values that graph assembly cannot infer.

Produce an honest early valid draft before request 48 or 650 seconds, then refine it while remaining below **64 requests and 900 seconds**. A partial graph with explicit gaps is better than a late or invented complete one.

Keep these states distinct:

- `missing`: the required input was not supplied;
- `unreadable`: supplied, but the available PDF/OCR path could not recover it;
- `partial`: some pages or sections were recovered;
- `not_reported`: the source is readable but does not report the requested item;
- `readable`: the needed content was recovered and checked.

Record unreadable/missing inputs in source status and uncertainties. Record `not_reported` on the relevant claim or limitation, not as an extraction failure. Set overall status to `partial` rather than implying complete coverage when material remains unread or unresolved.

## Task-adaptive response rule

Read the requested deliverable before graph construction. For **QA, translation, or extraction**, give the direct contracted answer first, with concise anchors; do not replace the answer with a graph. For **notes or literature-reading requests**, produce the argument graph as the main artifact and optionally use it to enrich notes. Never make optional graph enrichment displace a required direct answer.

## Section-native graph workflow

1. Register each source and its recovery status. Build an ordered section inventory from the actual document; keep supplied headings and identify each section's purpose.
2. Read locally before abstracting: capture the section's claim, the actual observation/analysis used as evidence, the reasoning or methodological warrant connecting them, explicit limitations, and transitions to the next move.
3. Create stable node IDs and typed edges as specified in [references/graph-schema.md](references/graph-schema.md). Keep nodes in source section order; distinguish reported statements from reader inference.
4. Give every substantive node a precise anchor: `source_id`, a section/paragraph locator, a short contiguous verbatim quote, and optional normalized offsets/page. The quote is evidence of location, not proof of the proposition.
5. Apply the semantic review in [references/review-playbook.md](references/review-playbook.md). Machine checks cannot establish entailment, causality, scientific validity, or completeness of interpretation.
6. Run deterministic audits, render section-aligned Markdown, assemble `result.json`, then validate it against the actual contract. Fail honestly on malformed input or broken references.

## Deliverables and tools

For notes, the main deliverables are `argument_graph.json`, `graph.md`, and `notes.md`, plus `result.json` and an audit report. Include source/status/uncertainty/change records in allowed result fields or auxiliary artifacts. Use the runnable scripts:

```bash
K=/skills/weekly-skill  # 若实际安装路径不同，设为本 SKILL.md 所在目录
python3 "$K/scripts/argument_loom.py" assemble \
  --case /input/case.json --source /app/work/source.json \
  --graph /app/work/graph.json --output-dir /app/output
python3 "$K/scripts/argument_loom.py" check-result \
  --case /input/case.json --result /app/output/result.json \
  --output /app/output/contract-audit.json
```

For QA/translation/extraction contracts, add `--response /app/work/response.json` to the `assemble` command. The response is a JSON object merged over generated graph/source/uncertainty/change defaults, so direct answers survive closed schemas. Supply every declared top-level property not generated by the assembler, even when it is absent from the schema's `required` array. Undeclared overlay keys are rejected in a closed contract. Overall status is chosen from the actual enum (`success` or `complete`, `partial`, `failed`) and a response cannot upgrade source gaps or open core-claim review.

The assembler writes the audit and, whenever the contract can represent the outcome, a contract-valid best `partial`/`failed` result before exiting nonzero on invalid or unreadable graph input. It preserves a parseable invalid graph without repair and emits diagnostic Markdown rather than inventing nodes or edges. It checks anchor containment/offsets, source and section consistency, references and relation topology, core-claim evidence/warrant/limitation coverage, and a practical JSON Schema subset for the output contract. It does **not** certify semantic truth. Source gaps and unreviewed/disputed core claims prevent `success`/`complete` even when structural validation passes.

Set `"synthetic": true` on the case **or** source to request synthetic/non-official banners. The default is real/non-synthetic: never infer a synthetic label from filenames or graph IDs. Source-status section counts come from the actual section registry.

## Runnable non-official example

`examples/synthetic` contains a unique tiny fictional paper, not an official answer and not copied from any paper. From the skill root run:

```bash
bash examples/synthetic/run_example.sh
bash examples/synthetic/run_example.sh /tmp/argument-loom-output
python3 scripts/test_argument_loom.py
```

The shell runner uses skill-relative paths, accepts an output root, and really executes assembly/rendering. The Python self-test runs a positive case and deliberate transient broken fixtures outside the bundle; success means those broken cases are detected, not that they pass. Generated example artifacts are inspectable in `examples/synthetic/output` and are explicitly labelled **合成示例 / non-official / SYNTHETIC EXAMPLE**.
