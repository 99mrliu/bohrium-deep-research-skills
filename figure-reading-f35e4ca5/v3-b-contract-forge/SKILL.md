---
name: contract-forged-figure-reading
description: Output-contract engineering for scientific figure reading — parse any output_contract into a flat field plan, materialize an early skeleton result.json, fill via logged merges, machine-lint with auto status downgrade. Triggers: 输出契约, result.json 校验, output contract, schema validation, delivery lint, 交付完整性.
---

# Contract-Forged Figure Reading

**Core idea.** Under a hard budget, most lost points are *delivery* failures, not reading
failures: null contract fields, wrong shape, missing `case_id`, claims without locators,
`status: "success"` claimed over empty fields. This skill makes the `output_contract`
itself the governed artifact: parse it into a flat field plan, materialize a valid
skeleton `result.json` at minute zero, fill fields through a logged merge mechanism, and
machine-lint the final deliverable against the contract with automatic status downgrade.
Reading and interpreting figures is the agent's job; this skill guarantees that whatever
was read is delivered completely, in-contract, and auditably. 交付契约工程：先成骨、再填肉、后验尸。

## Runtime contract

Read `/input/case.json` and `/input/task.md` first; the case's `output_contract` defines the exact result fields (any shape — dict, list, or mixed). Work in `/app/work`; final artifacts belong in `/app/output`, including `result.json` carrying the original `case_id` and every output_contract field. Budget is tight (~900 s, 64 model calls): write a valid **partial** result.json early; improve it in place and keep `status` honest (`success` only when every contract field is filled and every claim is locatable; otherwise `partial` with explicit limits). The case ships ONE original figure image plus all original tables; any figure mentioned in text or captions whose pixels are not provided is a declared gap — list it, never reconstruct it. If paths differ outside the harness, pass the real paths with the CLI flags.

## Dependencies

python3 standard library only for the three scripts in `scripts/` (json, argparse, re,
os, sys, datetime — no numpy needed here). The demo generator in `examples/` additionally
uses matplotlib to draw its synthetic figure. No network, no pip.

## Workflow

0. **Parse contract + write skeleton** (this IS the early partial result):
   `python3 scripts/contract_parse.py --case /input/case.json --task /input/task.md --work /app/work --out /app/output`
   → `contract_plan.json` (flat field list) + `result_skeleton.json` (contract-shaped,
   null leaves, `case_id` and `status: "partial"` already present). Copy/rename the
   skeleton to `result.json` immediately — a valid partial deliverable now exists.
1. **Plan reading work from the field plan.** For each plan entry decide what evidence
   the field needs: a figure region (axis labels, legend, curve), a table, or text. See
   `references/contract_field_semantics.md`. Spend model calls only on fields that exist
   in the plan; anything read that has no plan path goes to `uncertainty`, not into
   invented contract keys.
2. **Fill fields via fragments with change logging:**
   `python3 scripts/contract_fill.py --skeleton /app/output/result.json --fragment frag.json --work /app/work`
   Fragments are deep-merged; a top-level `_source` map attaches a locator to each
   changed leaf; every changed leaf is appended to `change_log.jsonl`. `case_id` is
   write-protected. Fill in several small fragments as evidence accumulates.
3. **Lint:**
   `python3 scripts/contract_lint.py --case /input/case.json --result /app/output/result.json --plan /app/work/contract_plan.json`
   Exit 0 = clean; 2 = violations and/or an automatic `success → partial` downgrade
   (result.json rewritten); 1 = fatal (case_id mismatch). Read `lint_report.json`, fix
   what is fixable, and for unfixable fields write an explicit reason into `uncertainty`
   (see `references/status_honesty.md`).
4. **Deliver** to `/app/output`: final `result.json` plus `lint_report.json` and
   `change_log.jsonl` as audit artifacts. The delivery set is: deliverable + proof it
   was checked + proof of how it was built.

## Failure catalogue

| Failure | Handling |
|---|---|
| `output_contract` missing | `contract_parse.py` exits 2 and falls back to a minimal contract derived from task.md question lines; the plan is flagged `"degraded": true`; say so in `uncertainty`. |
| Contract shape exotic (deeply nested lists, top-level list) | Lists flatten to `<path>[]` element templates (first element governs); a non-dict top level is wrapped under `contract_payload` so honesty fields survive; note the exotic shape in `uncertainty`. |
| Field unfillable (evidence absent) | Explicit `null` + a reason entry in `uncertainty` with the field path — never invent a value; lint treats documented nulls as non-violations for coverage, but they still block `success`. |
| Status conflict (`success` over empty/unresolved fields) | `contract_lint.py` auto-downgrades to `partial`, rewrites result.json, records the downgrade in `lint_report.json`. |
| `case_id` mismatch | Fatal: lint exits 1; the deliverable is void until the original `case_id` is restored. `contract_fill.py` refuses case_id changes. |

## Limits

- The skill does **not** read figures, tables, or text. Interpretation — what an axis
  says, what a curve means, what the answer is — remains entirely the agent's job. The
  skill governs delivery, not perception.
- Honesty rules: `success` only when every required contract field is filled and every
  claim is locatable; never reconstruct figures whose pixels were not shipped (declared
  gaps are listed, not redrawn); never invent values to satisfy the contract — an
  honest `null` with a reason beats a fabricated number every time; `case_id` is
  immutable.
