---
name: evidence-interval-reconciliation
description: Reconcile multi-document comparisons by validating evidence intervals that bind each value to its metric, material, pollutant, experimental budget, provenance, and uncertainty before rendering any matrix or synthesis.
---

# Evidence interval reconciliation

Use this Skill when several papers or reports must be compared without separating a result from the conditions that make it meaningful. The unit of work is a **claim with evidence intervals**, not a bare extracted number. This is not corpus duplicate detection and not a generic replay script.

## Runtime and boundaries

- Read `/input/case.json`, `/input/task.md`, `/input/comparison-workorder.json`, and every whitelisted PDF/text source. Work only in `/app/work`; write final deliverables only to `/app/output`.
- The supplied example is synthetic and uses plain text only. `pdftotext` is optional for real PDFs; never install it or any other dependency during a run.
- Never upload, submit, use credentials, or modify files outside the designated input/work/output locations.
- At most 50 UTF-8 text deliverable files are allowed by this bundle convention. Do not create symlinks or binary outputs.

## Procedure

1. **Index before interpreting.** Run `scripts/index_sources.py` (or `run_case.py`) to create `/app/work/source-index.json`. Use exact `source_document_id` values and stable `paragraph_id`, page, offsets, and content hashes. Record unreadable or unsupported sources as uncertainty rather than inventing coverage.
2. **Read task and workorder constraints first.** Identify the requested task, comparison IDs, metric definitions, requested units, material and pollutant scope, and experimental budget. A numerically similar result under another pollutant or budget is not an answer to the same cell.
3. **Find the metric definition first.** Locate the definition/caption/header interval when present. Then capture the result support interval. Attach the *smallest sufficient* context interval that supplies material, pollutant, metric, unit, and budget. Values and qualifiers may occur in different sentences, paragraphs, table captions, and headers.
4. **Create evidence records.** Follow `references/evidence-schema.md`. Each quantitative record has one `support` interval, one or more `context` intervals, and optionally a `definition` interval. Map every qualifier to the exact spans that establish it. Retain original quote text and offsets; normalized matching is only an equivalence check.
5. **Classify evidence honestly.** Use `direct`, `derived`, `inference`, or `absent`.
   - Direct values must occur literally in their support interval after stable Unicode/whitespace/hyphen normalization.
   - Derived values must provide operands, source-span references, formula, and result unit; the validator independently evaluates the restricted arithmetic formula.
   - Agent inference remains labelled inference and is excluded from factual quantitative synthesis.
   - `not_reported` is an absence conclusion, not a fake quotation. It needs a complete searched paragraph scope and queries, with `paragraph_id: null` and no support span.
6. **Run independent completeness and conflict tests.** Validate document IDs, paragraph IDs, hashes, offsets, normalized quotes, roles, qualifier bindings, formulas, task/metric/unit/material/pollutant/budget compatibility, and absence scope. Different values for the same claim within one paper must share a conflict group and remain visible; never silently select one.
7. **Render only validated records.** The renderer emits the common-field matrix for every indexed document, the evidence ledger, sources, uncertainty, and change records. It retains `not_reported`, `noncomparable`, conflicts, and inference labels. It never pools unlike materials, datasets, dyes/pollutants, budgets, metrics, or units. Record-level comparisons and `noncomparable` alone do **not** force partial status.
8. **Assemble the dynamic contract.** Include the exact `case_id`, every field requested by list- or dictionary-shaped `output_contract`, `status` (`success`, `partial`, or `failed`), `sources`, `uncertainty`, and `change_records`. Unknown requested fields receive an explicit empty placeholder and uncertainty, causing partial status rather than silent omission.

## Commands

Real runtime (after writing `/app/work/evidence.json`):

```sh
python3 scripts/run_case.py --input /input --work /app/work --output /app/output
```

Explicit evidence path and separate validation are also supported:

```sh
python3 scripts/index_sources.py --input /input --output /app/work/source-index.json
python3 scripts/validate_and_render.py --input /input --index /app/work/source-index.json --evidence /app/work/evidence.json --output /app/output
```

Run the complete offline example and its negative tests:

```sh
sh examples/run_example.sh
```

See `references/protocol.md` for reading and conflict rules, `references/evidence-schema.md` for record structure, and `references/runtime-contract.md` for status and output behavior.
