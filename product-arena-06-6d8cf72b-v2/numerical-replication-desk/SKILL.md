---
name: numerical-replication-desk
description: Recompute and audit numerical claims in literature notes with anchored Decimal calculations, provenance labels, conflicts, and honest original-figure comparison.
---

# Numerical Replication Desk

Use this Skill when a task asks whether reported numbers are internally reproducible, when body/table/figure values disagree, or when a numerical comparison plot would help. This is a numerical verification workflow, not generic evidence chunking, a scope graph, or schema-only checking.

## Runtime and safety

- Read the real `/input/case.json`, `/input/task.md`, and `/input/materials`. Write intermediate work only in `/app/work` and deliverables only in `/app/output` unless the runner explicitly supplies equivalent paths.
- Use only platform-provided PDF text extraction and page/figure rendering tools. Do not use personal paths, network access, package installation, or non-platform PDF renderers.
- Produce an early draft in fewer than 64 model calls and within 900 seconds. Start with direct QA, then verify decision-relevant numbers. A partial, source-anchored answer is better than late or invented completeness.
- Distinguish `author_reported`, `independently_calculated`, `reader_inference`, `not_reported`, and `missing`. Never turn a calculation or visual estimate into an author-reported value. Use `missing` for an unsupplied input and `not_reported` for a value omitted by a supplied source.
- Never invent confidence intervals, standard errors, p-values, sample sizes, uncertainty distributions, or independence. Repeated measurements require an explicit non-independence caveat.
- Run the Python engine with Python 3.9+ standard library only. It uses `Decimal` and a fixed operation allowlist; it never evaluates expressions with `eval` or `exec`.

## Direct-QA-first workflow

1. Read `case.json` and `task.md`. Audit the actual case's complete `output_contract` before execution: every declared property, required list, nested object type, const/enum, supported alternative/reference, string/array/numeric constraint, and recursive `additionalProperties: false`. Unsupported keywords are rejected, never ignored. The final root object must contain `case_id` and exactly the declared contract fields.
2. Write the direct answer first. Mark unanswered parts `not_reported` or `partial`; do not delay them while building a ledger. Adapt effort to the task: verify only numbers that affect the requested answer unless a full audit is requested.
3. Extract numerical tuples, not isolated numbers: value, row, column, condition, unit, source ID, page/table/figure locator, a short verbatim quote, and its exact `char_start`/`char_end` Unicode code-point region in the source text. The engine checks only that region; a legacy locator is explicitly `locator_not_checked`, and bad/unreviewed regions fail dependent claims closed. Preserve signs, denominators, baseline/final roles, displayed precision, and whether a value is an error or a score.
4. Record body, table, and figure instances separately. Reconcile them only after unit and condition alignment. Report every conflict explicitly; never silently select a convenient value.
5. Create a ledger following `references/ledger-schema.md`. For each check define safe operands, formula, direction, expected value, tolerance, rounding, and all input anchors. Use `references/math-and-rounding.md` to distinguish relative percent change from percentage points.
6. Run `scripts/nrd.py verify` (ledger-only) or `scripts/nrd.py run` (contract result). Inspect `verification.json` and `verification.md`; investigate mismatches, unreadable/missing sources, quote failures, and contract errors. A mismatch is a result to report, not something to repair by changing the source number.
7. For an arbitrary case, prepare a response JSON object for the contract-specific prose fields and pass `--response`. The engine overlays it on an honest partial skeleton, injects case/computation/source/change data for recognized fields, and recursively validates const/enum, references/alternatives, string/array constraints, and numeric bounds. Without a response, unanswered prose remains explicitly `not_reported` and status remains partial. Output status honors the declared vocabulary (`complete` or `success`, with `partial`/`failed` as appropriate); it never forces an undeclared or dishonest `complete`.
8. Independently reread key arithmetic and the generated result. State limitations for OCR, unit conversion, significant figures, rounding, source access, and repeated measurements.

## CLI

```bash
K=/skills/weekly-skill  # 若实际安装路径不同，设为本 SKILL.md 所在目录
python3 "$K/scripts/nrd.py" verify \
  --ledger /app/work/numeric_ledger.json \
  --output-dir /app/output \
  --fail-on-mismatch

python3 "$K/scripts/nrd.py" run \
  --case /input/case.json \
  --task /input/task.md \
  --materials /input/materials \
  --output-dir /app/output \
  --response /app/work/response.json \
  --fail-on-mismatch
```

`--response` is optional. `--case` defaults to `/input/case.json`, `--task` to `/input/task.md`, `--materials` to `/input/materials`, and `--output-dir` to `/app/output` in `run` mode. Malformed input exits 2. `--fail-on-mismatch` exits 1 after writing an honest mismatch result. A ledger may be inline as `numeric_ledger` in the case or referenced by `numeric_ledger_path` relative to the case file.

## Original-page and figure checks

Generate a comparison only when the task asks for one or the compared numbers materially matter. Follow `references/visual-comparison-policy.md`.

- Extract numbers from the original PDF text first, then inspect the original rendered page and a tight figure/table crop. Record page number, figure/table identifier, crop path, axis/legend units, and the exact values checked.
- Save original renders/crops and derived comparison artifacts under `/app/output`. Supply platform-created image paths through `visual_comparison.original_render` and `original_crop`; the engine copies supplied images but does not render PDFs itself.
- A generated plot is a derived comparison, not a recreation of the original and not evidence of correctness. If an original figure was not supplied, mark its source values, render, crop, and review `missing`; use `unreadable` for a supplied artifact that cannot be read. Reserve `not_reported` for omissions within a supplied source.
- Do not fabricate an original figure. Do not claim an original-to-derived agreement unless a person/model actually reviewed the original crop and recorded the comparison.

## Minimal synthetic example

The bundled example is entirely fictional and labelled `SYNTHETIC` in its source, task, ledger, result, and SVG. It compares low/high-temperature errors for methods A/B and includes a repeated-measures caveat.

```bash
sh scripts/run_example.sh                 # bundled examples/synthetic/output
sh scripts/run_example.sh /app/output     # explicit output directory
python3 -m unittest discover -s tests -v # standard-library CLI regression suite
```

The example independently checks that 40 to 30 is a 25% relative reduction and a 10 percentage-point reduction. Its derived SVG is not an original figure and provides no independent validation of the fictional source.
