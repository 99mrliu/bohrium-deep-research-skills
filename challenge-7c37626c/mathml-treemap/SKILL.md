---
name: mathml-treemap
description: Reversible MathML JSON IR with deterministic formula extraction, faithful LaTeX rendering, structural roundtrip verification, independent publisher-text checks, and contract-safe partial result assembly.
---

# MathML Treemap

Use this skill to make MathML the evidence backbone of formula analysis. Its center of gravity is a canonical, reversible intermediate representation (IR), not a generic research checklist and not file-authenticity hashing. Extraction supplies formula evidence only; it does **not** answer variable definitions, derivation logic, numerical claims, or scientific interpretation.

## Non-negotiable evidence rules

1. Read the original `/input/case.json` and `/input/task.md` first. Preserve the exact `case_id` and inspect the dynamic `output_contract`, including `required_fields`, `field_types`, and `status_enum` when present.
2. For C01/C03, use the case's `publisher-source.xml` and `source-formulas.xml` MathML as available. For C02, which lacks formula/data evidence, emit explicit `insufficient_evidence`; do not invent a formula, value, derivation, or citation. Apply the same no-formula rule to every case.
3. Never infer a missing formula from an expected answer, a publisher `alttext`, a `tex-math` sibling, an image description, or another paper. Publisher strings are independent comparisons only—even exact agreement is not proof of structure, semantics, or scientific validity.
4. Extract **every** `<math>` node from every discovered source. Keep duplicates as distinct source occurrences. Use `formula_key`, source id/label/section, and ordered path when authoring downstream evidence.
5. Read the IR, all render issues, every structural discrepancy, and the publisher-text statuses before making claims. Unknown tags, invalid arity, and mismatches are partial evidence, not silent success.
6. Populate scientific fields from actual agent-authored analysis grounded in source evidence. LaTeX is notation conversion, not a variable/derivation/numeric analysis.

## Runtime layout

Run commands from the directory containing this `SKILL.md`; scripts resolve their sibling modules from `scripts/` and use no other bundle. All implementation code is Python stdlib. Inputs are read-only; intermediate evidence belongs in `/app/work`, and final files belong in `/app/output`.

```bash
# Original runtime inputs and destinations
python3 scripts/extract_mathml.py \
  --case /input/case.json \
  --task /input/task.md \
  --input-root /input \
  --work /app/work
```

If source discovery cannot resolve a case-relative path, pass each original source explicitly (repeat `--source`):

```bash
python3 scripts/extract_mathml.py \
  --case /input/case.json --task /input/task.md \
  --input-root /input --work /app/work \
  --source /input/publisher-source.xml \
  --source /input/source-formulas.xml
```

Extraction exit codes:

- `0`: all supported roundtrips passed, **or** no formula was found and `insufficient_evidence` was written;
- `2`: unsupported/malformed MathML or a roundtrip mismatch was retained and reported;
- other nonzero exceptions indicate unreadable/invalid input or an I/O failure.

## Evidence tree and mandatory verification

Extraction writes:

```text
/app/work/mathml/
  catalog.json                 # all nodes, metadata, IR, LaTeX, checks, locators
  catalog.md                   # human-readable formula evidence catalog
  summary.json                 # compact status/count summary
  ir/<formula_key>.json        # canonical JSON IR for each math node
  latex/<formula_key>.tex      # generated notation, never publisher text copied as truth
  roundtrip/<formula_key>.json # every structural discrepancy and unsupported node
```

Recompute verification from the IR instead of trusting stored extraction status:

```bash
python3 scripts/verify_roundtrip.py \
  --catalog /app/work/mathml/catalog.json --strict
```

This writes `/app/work/mathml/roundtrip-verification.json`. `--strict` returns `2` if any formula is unsupported or has any discrepancy. That result does not erase the partial catalog: inspect it and report the limitation. A structurally equal roundtrip containing an unsupported tag remains `unsupported`, not `pass`.

The verifier checks `IR -> MathML -> IR`. Canonical equality preserves node tags, attributes, text, recursive child order, and operator token data. See [references/IR_SPEC.md](references/IR_SPEC.md) for exact preservation and whitespace/namespace boundaries.

## Author scientific analysis separately

After inspecting the catalog and original source context, write an actual analysis object such as `/app/work/agent_analysis.json`. Match the dynamic output contract rather than blindly copying this illustration:

```json
{
  "status": "partial",
  "formula_analysis": [
    {
      "formula_key": "USE_AN_ACTUAL_CATALOG_KEY",
      "source_id": "USE_SOURCE_EVIDENCE",
      "latex": "REVIEWED_GENERATED_LATEX_FROM_ACTUAL_CATALOG",
      "interpretation": "Agent-authored, source-grounded interpretation"
    }
  ],
  "variable_analysis": [],
  "derivation_analysis": [],
  "numeric_analysis": {
    "status": "insufficient_evidence",
    "reason": "State exactly which values, units, assumptions, or steps are absent."
  }
}
```

Do not submit that template unedited. Do not use `USE_AN_ACTUAL_CATALOG_KEY` or `REVIEWED_GENERATED_LATEX_FROM_ACTUAL_CATALOG` literally; use actual catalog values after reviewing the IR and renderer issues. Empty analyses must state why; a numeric zero is not an honest missing-value marker. Widths, units, domains, variable definitions, derivation justifications, and numerical results require evidence beyond an IR.

Assemble the final dynamic result:

```bash
python3 scripts/assemble_result.py \
  --case /input/case.json \
  --task /input/task.md \
  --catalog /app/work/mathml/catalog.json \
  --analysis /app/work/agent_analysis.json \
  --output /app/output/result.json
```

The assembler:

- takes `case_id` only from `case.json` and rejects a case/catalog mismatch;
- finds `output_contract` in `case.json`, or in JSON/a JSON fence in `task.md`;
- supplies every declared/required field and validates declared field types;
- preserves agent-authored fields without pretending generated LaTeX answers them;
- automatically fills only factual extraction-summary fields, never scientific claims;
- forces `insufficient_evidence` when no MathML is found, using the contract's allowed status value where possible;
- writes `/app/output/result_validation.json` listing missing authored fields and type issues.

For an early honest partial before analysis is ready, omit `--analysis`. Arrays/objects/strings receive explicit empty/insufficient placeholders; types with no truthful placeholder receive `null` and a reported validation error instead of a fabricated scalar. A returned `2` means the partial result exists but contract type/presence issues remain. Inspect both JSON files before submitting.

## Limitations

- The supported reversible/rendering subset is `math`, `mrow`, `mfrac`, `msub`, `msup`, `msubsup`, `msqrt`, `mroot`, `mfenced`, `munder`, `mover`, `munderover`, `mtable`, `mtr`, `mlabeledtr`, `mtd`, `mi`, `mn`, `mo`, `mtext`, `mstyle`, `mpadded`, `mphantom`, `mspace`, `menclose`, `semantics`, `annotation`, and `annotation-xml`. Other tags remain in IR and XML but produce explicit LaTeX markers and a non-pass verification status.
- IR uses XML local tag names; attribute namespaces and values are retained, but element namespace URIs/prefixes, comments, processing instructions, and child tails are not represented. Element text is retained. No Unicode compatibility normalization or NFKC merging is performed. Read the spec before treating roundtrip status as full XML-document equivalence.
- The LaTeX renderer deliberately uses a conventional core (`matrix`, `\underset`, `\overset`, `\mathit`) and explicit codepoint operator mappings. It preserves structure, not a publisher's visual styling or complete MathML semantic nuances. Multi-character `mi` tokens remain one identifier. Fences and operand braces are explicit.
- `munder`/`mover` rendering does not infer accents or limits from context. Invalid arity gets an `INVALID` marker; unusual mixed token content gets an issue. `mtable`/`mlabeledtr` renders as `matrix` and ignores advanced table styling in LaTeX even though attributes remain in IR. `semantics` annotations remain in IR but are not visible operands. Only radical and boxed `menclose` notations have direct notation mappings; other notations produce a visible review marker.
- The source walker discovers only files named `publisher-source.xml` or `source-formulas.xml`, plus explicit `--source` arguments. It does not OCR images, evaluate math, read external entities, or infer formulas from prose.
- Advisory `alttext`/`tex-math` comparisons support exact, whitespace-only, mismatch, and absent states; they are never used to repair or overwrite generated LaTeX/IR.
- A successful canonical roundtrip proves only lossless traversal of the defined IR through the bundled MathML serializer/parser. It does not prove scientific correctness, semantic equivalence to publisher text, derivation validity, numerical validity, or completeness outside the discovered files.

## Fully synthetic verification

No file in `examples/` is an actual challenge answer. Run all normal, unknown-tag failure, and no-formula tests from the bundle root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_synthetic_example.py
```

The normal test creates a real `examples/synthetic/output/result.json`, a Markdown catalog, IR/LaTeX files, and passing roundtrip reports. It includes a nested fraction, `msubsup`, a multi-character identifier, matrix, and explicit fences. The expected-failure test introduces an invented `<mystery>` node and contradictory publisher `alttext`: extraction and strict verification both return `2`, an unsupported marker is rendered, and the publisher comparison remains a mismatch. The disposable no-formula test assembles an `insufficient_evidence` result without scientific invention.
