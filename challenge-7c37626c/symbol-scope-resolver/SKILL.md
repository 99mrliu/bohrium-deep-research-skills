---
name: symbol-scope-resolver
description: Ground scientific symbols in discourse-local scopes, audit full MathML identities (base glyph plus scripts), and produce evidence-checked variable/unit/range tables. Use for publisher XML with source formula MathML, symbol disambiguation across sections, quantified-variable provenance, definition conflicts, and cases where missing formula representation requires honest partial or insufficient-evidence output rather than OCR or invented values.
---

# Symbol Scope Resolver

Resolve what each **locally scoped symbol occurrence** means and which quantities
are actually reported. This is a provenance task, **not formula OCR**. Preserve
source MathML as formula evidence; never reconstruct missing formulae from images,
plain-text guesses, memory, or expected physics.

## Inputs and non-negotiable case behavior

The runtime uses `/input/case.json`, `/input/task.md`, `/app/work`, and
`/app/output`. Read the task and actual case contract before analysis. C01 and C03
must be grounded in their actual publisher XML and source MathML. C02 has no
formula representation and no supplied values: return `partial` or
`insufficient_evidence` according to its status enum, use null/not-reported for
quantities, and never guess or fill zero. These labels are not interchangeable;
prefer `insufficient_evidence` when C02's contract provides it.

## Workflow

### 1. Build the deterministic evidence ledger

Set `SKILL_DIR` to the directory containing this file, then run:

```bash
mkdir -p /app/work /app/output
python3 "$SKILL_DIR/scripts/ledger.py" \
  --case /input/case.json --task /input/task.md --work /app/work
```

Read `/app/work/ledger.md` and `ledger.json`. The ledger contains:

- ordered document/section, paragraph, and exact-substring sentence locators;
- every MathML or explicitly non-MathML formula occurrence, source pointer,
  surrounding paragraph/sentence context, and original extracted XML subtree;
- symbol occurrences grouped by **document + local section + canonical full
  symbol + complete script structure**;
- English/Chinese definition, unit, and range candidates.

A candidate is an evidence lead with `candidate_only: true` and
`confirmation_required: true`. It is **not** an auto-confirmed definition.

### 2. Author `bindings.json` from the evidence

Copy `bindings.template.json` to `/app/work/bindings.json` as a checklist, then
write the analysis yourself. Do not write a script that blindly approves all
candidates. For each relevant scoped symbol instance:

1. Preserve `symbol_instance_id`, `section_id`, `canonical`, `base_glyph`, and
   `scripts` exactly. `r`, `r_{1}`, and `r_{2}` are different identities; plain
   `r` in two sections also needs two independent bindings.
2. Select one category: `direct_source_definition`, `contextual_inference`,
   `common_knowledge_external`, `not_reported`, or `conflict`.
3. A direct definition must select a real same-scope definition candidate and
   repeat its exact quote and full locator. Quote text must remain a literal
   substring of its located sentence/paragraph.
4. A contextual inference must state `inference_reason`. External common
   knowledge must state `external_basis` and
   `attribution: external_not_paper`; never attach paper evidence to it.
5. Give units and ranges their **own** provenance objects. Literal values require
   literal same-scope evidence quotes. An inferred quantity must be labeled as
   inference with a reason. Use `{ "value": null,
   "provenance": "not_reported", "reason": "..." }` when absent.
6. Keep every competing claim in `conflicts`; never erase a conflict or impose a
   single global definition across source scopes.

For **every formula occurrence**, supply a coverage entry: either `covered: true`
with all scoped symbol instance IDs from that occurrence, or `excluded: true`
with an explicit reason. Do not silently skip a formula.

See `references/bindings-schema.md`, `references/scope-resolution.md`, and
`references/evidence-and-validation.md` for exact requirements and examples.

### 3. Validate and emit

```bash
python3 "$SKILL_DIR/scripts/finalize.py" \
  --case /input/case.json --work /app/work --output /app/output
```

This writes `variable_table.md`, `variable_table.json`, `result.json`, and a
validation report in work. Exit 2 means errors; normal mode still retains honest
non-success outputs. Inspect all files before finishing.

If time or evidence runs short, finalize **early** with the authored partial
bindings (or, as a last resort, the template) rather than not writing a result.
Incomplete coverage and unbound symbols will remain visible as errors/warnings;
the result will be partial/invalid, not silently complete. The result uses the
case's exact `case_id`, emits every field named by `required_fields` and
`field_types`, honors `field_types`, and selects status from `status_enum`.
Undetermined numeric or boolean values stay null, never zero/false placeholders.
Extra agent-authored contract values may be supplied under `output_fields`.

## Final gates

- Every formula occurrence is covered or explicitly excluded.
- Direct definitions have selected same-scope candidates and exact quotes.
- Units/ranges have independent literal/inferred/external provenance or are null.
- Competing scopes and conflicts survive in both variable tables and result.
- C02 is partial/insufficient with no fabricated formula or zero-filled value.
- Result status is allowed by the contract and validation has no hidden errors.
