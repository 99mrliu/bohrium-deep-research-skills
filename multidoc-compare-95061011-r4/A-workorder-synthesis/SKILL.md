---
name: workorder-synthesis
description: Answer multi-document comparison workorders by dynamically planning requested deliverables and output fields, synthesizing only comparable evidence, and assembling a source-located matrix, integration report, and result JSON.
---

# Workorder-adaptive comparison synthesis

The deliverable is the answer to **this case's questions**, not a generic extraction table. Treat the supplied workorder as the definition of scope, questions, terminology, and output keys. Do not impose a photocatalysis schema or any other fixed domain schema. Noncomparability can be the correct, complete scientific conclusion.

## Operating constraints

Work only under `/app/work`; write final artifacts to `/app/output`. Read the real `/input/case.json`, `/input/task.md`, `/input/comparison-workorder.json`, and every in-scope corpus document. No network retrieval is needed for the supplied corpus. Plan for at most 64 model requests and a 900-second wall-clock budget: inspect the workorder first, batch source reading by question, and reserve time for assembly and the final checklist.

Required final files:

- `/app/output/comparison-matrix.md`
- `/app/output/integration-report.md`
- `/app/output/result.json`

`result.json` must retain `case_id` verbatim, every key named by the original `output_contract` with its original spelling and nesting, plus honest `status`, `sources`, `uncertainty`, and `change_records`. Agent-authored supplemental fields may be retained, but never rename or replace a contract key.

## 1. Discover the requested response before extracting values

Read `task.md` and the workorder together. Distinguish:

1. Requested deliverables and audiences.
2. Every explicit question, sub-question, requested comparison, decision, or recommendation.
3. Included and excluded documents; preserve exact `source_document_id` strings.
4. Workorder-specific definitions, thresholds, time points, denominators, units, budgets, and meanings of equivalent conditions.
5. The original `output_contract` and each field's definition and type.

Run:

```bash
python3 /skills/weekly-skill/scripts/plan_workorder.py \
  --case /input/case.json \
  --task /input/task.md \
  --workorder /input/comparison-workorder.json \
  --output /app/work/response-plan.json
```

This is a planning skeleton, not the answer. In `/app/work/response-plan.json`, complete `agent_answer_and_mapping` and `evidence_cell_ids` after reading sources. Add any implicit deliverable or mapping the skeleton missed. Build one plan row per asked question: exact result fields, in-scope documents needed, needed dimensions, candidate evidence cells, comparison/synthesis decision, and uncertainties. If the workorder gives only prose questions, use its wording to create those rows yourself.

The planner accepts output contracts expressed as a list of names, a list of field objects, a mapping from key to specification, `{"fields": ...}`, or JSON-Schema-like `{"properties": ...}`. Inspect the actual plan rather than assuming a template.

## 2. Read the real sources and create quotable locators

For text sources, preserve the supplied paragraph identifiers. For PDFs, first try layout-preserving extraction into your working directory:

```bash
pdftotext -layout /input/DOCUMENT.pdf /app/work/source-text/DOCUMENT.txt
```

Inspect the extraction around every relevant table, heading, caption, and footnote. `-layout` spacing often matters for associating a value with its row and column. If text is absent, garbled, or a table/figure cannot be interpreted, render the relevant pages at useful resolution and inspect them visually; use OCR only as a fallback and cross-check OCR values against the rendering. Record page and paragraph/locator details in working notes. Do not silently proceed from a failed read.

The assembler consumes UTF-8 source texts with stable markers such as:

```text
[exact-source-id:p0001] Original paragraph text begins here...
```

Create these working texts under `/app/work/source-text` without changing the underlying wording. Each marker identifies one source paragraph; retain exact source paragraph IDs where available. Use exact source IDs in `/app/work/common-cells.json`, mapping each document to its relative text path. Quote a contiguous span from the identified paragraph for every reported key cell. Whitespace may be normalized, but wording and numbers may not be reconstructed from memory.

## 3. Author response-specific common cells

Use `/app/work/common-cells.json` with this flexible shape:

```json
{
  "documents": [
    {"source_document_id": "exact-id", "path": "exact-id.txt"}
  ],
  "cells": [
    {
      "cell_id": "unique-cell-id",
      "question_id": "workorder-question-id",
      "dimension": "dimension-needed-by-this-question",
      "source_document_id": "exact-id",
      "paragraph_id": "exact-source-id:p0001",
      "state": "reported",
      "value": "source-supported value",
      "quote": "exact contiguous source span",
      "task": "source-defined task or not_applicable reason",
      "metric": "source-defined metric or not_applicable reason",
      "units": "source units or not_applicable reason",
      "material": "source material/system or not_applicable reason",
      "pollutant": "target/analyte or not_applicable reason",
      "budget": "applicable budget condition or not_applicable reason"
    }
  ],
  "syntheses": [],
  "excluded_from_synthesis": []
}
```

Create only dimensions needed by the response plan, with additional metadata when useful (for example dataset, time point, dose, replication, page, or calculation basis). Do not manufacture empty boilerplate rows merely to imitate another case. Conversely, represent every in-scope document in every requested comparison dimension; if a dimension has no value in a source, include its truthful state rather than dropping the document.

Use states precisely:

- `reported`: the source explicitly supports this value; provide the exact quote.
- `not_reported`: the dimension applies, but the source does not provide it. Use value `"not_reported"`; no invented quote or value is needed.
- `not_applicable`: the dimension cannot apply to that source/question by definition. Explain why in `notes` or the report.
- `unclear`: relevant text exists but its meaning, locator, units, or mapping cannot be resolved confidently. Quote the ambiguous text when available and explain the ambiguity.
- `noncomparable`: a valid source-backed item or candidate result cannot be placed on the requested common basis. Retain it separately and explain the mismatch.

`not_reported`, `not_applicable`, `unclear`, and `noncomparable` are not missing work and must not be made up to fill a cell.

## 4. Decide whether synthesis is justified

Before **any** quantitative cross-document synthesis, test and record equality or justified equivalence of all six axes: `task`, `metric`, `units`, `material`, `pollutant`, and `budget`. Also inspect dataset identity, protocol, time point, denominators, and other case-specific conditions. If an axis is genuinely irrelevant, use an explicit, shared `not_applicable` value and reason rather than omitting the test. Do not equate materially different budgets or experimental constraints just because both have numbers.

Never pool unlike datasets, materials, pollutants/dyes, metrics, units, tasks, or budget conditions. Convert units only when the conversion is exact and show it in change records. Numerical proximity does not establish comparability. If comparability fails, keep individual values and set the conclusion to noncomparable/separate as appropriate; this can still produce `status: "success"`.

For a justified synthesis, add an agent-authored entry like:

```json
{
  "synthesis_id": "question-specific-mean",
  "question_id": "q2",
  "kind": "quantitative",
  "method": "arithmetic_mean",
  "member_cell_ids": ["cell-a", "cell-b"],
  "comparability_checks": {
    "task": true,
    "metric": true,
    "units": true,
    "material": true,
    "pollutant": true,
    "budget": true
  },
  "result": 50,
  "units": "example-unit",
  "statement": "State exactly which documents and basis this result represents."
}
```

The assembler independently compares member metadata and checks arithmetic means. For other methods, show the formula and calculate from the retained values yourself. Record every excluded candidate with its cell IDs and the precise mismatch in `excluded_from_synthesis`.

## 5. Author the answer, then assemble

Create `/app/work/agent-response.json`:

```json
{
  "fields": {
    "EXACT_ORIGINAL_CONTRACT_KEY": "answer shaped to its workorder definition"
  },
  "completion": {
    "requested_work_complete": true,
    "read_failures": [],
    "fatal_failure": false
  },
  "uncertainty": ["Specific unresolved issue, or an empty list if none."],
  "change_records": [
    {"change": "Excluded a candidate from pooling", "reason": "Exact comparability mismatch."}
  ]
}
```

Answer each contract field with the evidence-backed response, requested lists/objects, and source references where useful. `fields` may include useful supplemental keys, but standard result metadata keys (`case_id`, `status`, `sources`, `uncertainty`, `change_records`) are reserved. The assembler supplies those without mutating contract fields.

Status rules:

- `success`: every requested question/deliverable was addressed and all required sources were read. Noncomparability or `not_reported` alone still permits success.
- `partial`: requested work is incomplete or some required reads failed. Explain exactly what remains in `uncertainty` and `change_records`.
- `failed`: a fatal failure prevented a meaningful requested response. Keep every contract key with a truthful value rather than inventing content.

Run:

```bash
python3 /skills/weekly-skill/scripts/assemble_response.py \
  --case /input/case.json \
  --workorder /input/comparison-workorder.json \
  --response /app/work/agent-response.json \
  --cells /app/work/common-cells.json \
  --source-root /app/work/source-text \
  --output-dir /app/output
```

The command fails nonzero for a missing contract key, invalid/out-of-scope locator, quote not found in its cited paragraph, incomplete document coverage, single-document matrix, or unjustified quantitative pooling. It does not fail merely because a legitimate value is `not_reported` or a finding is noncomparable.

See `references/response-format.md` for the complete authoring contract and `references/evidence-and-pdf.md` for PDF checks and state examples. The clearly labelled example under `examples/` is synthetic and contains no official case answers.

## Final response checklist

Before finishing, reopen the task, workorder, source plan, and all three outputs. Check:

- [ ] Every explicit question, sub-question, decision, and requested deliverable has a visible response in `integration-report.md` and maps to the exact original output keys.
- [ ] All in-scope documents appear by exact `source_document_id`; every cited `paragraph_id` exists and every reported key cell has an exact source quote.
- [ ] Every requested comparison dimension is covered across all applicable documents. Absence is classified correctly, not silently omitted.
- [ ] Quantitative statements use only compatible task, metric, units, material, pollutant, budget, dataset, and case-specific conditions; excluded evidence remains visible.
- [ ] Qualitative consensus/disagreement is supported by the cited documents and does not overstate not-reported evidence as negative evidence.
- [ ] Contract keys and value types are unchanged, `case_id` is exact, and `sources`, `uncertainty`, and `change_records` describe this response rather than boilerplate.
- [ ] Status reflects completeness of requested work, not whether the scientific result was positive, comparable, or convenient.
- [ ] Tables contain only question-relevant rows, prose gives a direct conclusion first, and no generic template section substitutes for an answer.
- [ ] Final files are in `/app/output`, are readable UTF-8, and no official answer content came from the synthetic example.
