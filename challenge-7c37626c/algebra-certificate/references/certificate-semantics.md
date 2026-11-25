# Certificate semantics

## Scope

A certificate is a local-transition audit, not a global theorem prover and not a citation/provenance graph. Each transition must be written down explicitly. The checker never invents a missing step, repairs an equation, or generates an agent answer.

## Input schema

Top-level `derivation.json` fields:

- `case_id` (recommended) and `paper` (optional provenance metadata).
- `status`: normally `"ready"`. Use `"insufficient_evidence"` with no steps when C02 supplies no formulas; this is never treated as success.
- `steps`: ordered array of transition objects.
- Optional step `required` defaults to `true`. Only required steps gate final success.

Required step fields are `id`, `lhs` (or `source`), `rhs` (or `target`), `operation`, `justification`, `source_locator`, `assumptions`, `domain`, `dependencies`, and `origin`. `origin` must be `paper_explicit` or `reader_reconstruction`. Recognized operations are `expand`, `factor`, `simplify`, `rewrite`, `cancel`, `divide`, `substitute`, `add`, `multiply`, `sqrt_rule`, `log_rule`, and `power_rule`. `substitute` means symbolic rewriting, not numeric answer substitution. Unknown operations and malformed dependency graphs yield `invalid_operation`.

Expressions are parsed through a restricted Python AST walker with explicit arithmetic/comparison nodes and a small allowlist (`sqrt`, `log`, `exp`, `Abs`, `sin`, `cos`, `tan`). There is no call to Python `eval`, no attribute access, no import, and no arbitrary function execution. Original arithmetic is constructed with `evaluate=False` so a cancellation does not disappear before its domain is audited.

## Verdicts and precedence

`symbolic_equal` requires all of the following:

1. Valid input, safe parsing, known operation, and valid dependencies.
2. Required domain/side-condition licenses on both original expressions.
3. Symbolic simplification proving `lhs - rhs = 0`.

`falsified` means at least one concrete assignment satisfying every declared assumption makes the two sides unequal or makes exactly one side undefined. A counterexample takes precedence over a symbolic simplification that hid an illegal cancellation.

`invalid_operation` covers malformed steps, unsafe/unknown syntax, unknown operations, duplicate IDs, unknown dependencies, and dependency cycles. A dependency cycle affects every step in the cycle.

`missing_license` covers absent or insufficient denominator, cancellation, logarithm, root, or power conditions. Domain errors are partial evidence, never a pass.

`undetermined` covers an inconclusive symbolic check without a discovered counterexample, unparseable/undecidable assumptions, and an empty insufficient-evidence derivation. A SymPy Boolean returning `False` is not automatically a mathematical counterexample. Only a concrete evaluated counterexample or the exact SymPy `false` singleton can establish falsity; Python `False`, `None`, and unresolved relations are explained as undetermined.

The certificate additionally uses overall `unavailable` when SymPy cannot be imported (or during the explicit `--simulate-no-sympy` test). No unavailable dependency is reported as a pass.

## Symbolic and numeric roles

The symbolic phase tries conservative combinations of `simplify`, `powsimp`, `expand`, and `factor`. Numerical equality alone never upgrades a result. If symbolic simplification is inconclusive, or if original-domain hazards warrant counterexample search, deterministic rational assignments satisfying declarations are tested. Evaluation has explicit undefined/nonfinite handling. A result such as `0/0`, `zoo`, `nan`, or a magnitude overflow is not coerced to an ordinary numerical value.

## Overall certificate and fail-closed mapping

- Overall `symbolic_equal` requires at least one step and every required step to be `symbolic_equal`.
- Overall `falsified` takes precedence for a required falsified step.
- Required `invalid_operation` maps overall to `invalid_operation`.
- Missing SymPy maps to `unavailable`.
- Required `missing_license` maps overall to `missing_license`; otherwise any required `undetermined` maps overall to `undetermined`. Step-level detail preserves which license or proof remains unresolved.
- Optional failures remain visible but do not gate success. A derivation with zero steps is overall `undetermined` even if its top-level status says `ready`.

The finalizer independently requires `overall_status == "symbolic_equal"`, nonempty certified steps, every required step equal, and a complete agent-authored `answers.json`. It maps success, partial, or failed using **only members of task.md's dynamic `status_enum`**. Missing required agent values block success and are filled with typed placeholders, not inventions. Extra contract-outside fields are not silently added.

## Dynamic runtime contract

`init-result` is deliberately run before paper analysis to leave an honest partial artifact. Both it and `finalize` read a JSON `output_contract` object in `task.md`, including a fenced JSON block or an embedded raw object. Supported members are `required_fields` (ordered names), `field_types` (JSON type names by field), and `status_enum` (allowed statuses). `case_id` is always present, sourced from `/input/case.json`, `/input/input.json`, `/input/task.json`, or task text when available.

For finalization, answers are matched in this order: exact field name, exact key in `answers.fields`, and known semantic aliases such as `answer`/`final_answer`, `derivation`/`derivation_summary`, and `certificate`/`certificate_summary`. `status` is controlled by the checker, not by an agent-provided success claim. Type unions such as `["string", "null"]` are supported. Uncoercible or absent values receive safe typed defaults and prevent success.

A derived certificate summary can fill a certificate-like field only if the agent did not supply it; this summary states actual verdict counts. Derivation-like fields can receive the produced human Markdown only when the field is named accordingly. Task-specific prose and final answers are never reverse-engineered from formulas or certificates.

## Graceful dependency test

Run:

```bash
python scripts/algebra_certificate.py check \
  --derivation examples/synthetic/work/derivation.json \
  --certificate examples/synthetic/output/certificate-unavailable.json \
  --derivation-md examples/synthetic/output/derivation-unavailable.md \
  --simulate-no-sympy
```

The real written overall verdict is `unavailable`, each step is marked `undetermined`, and finalization cannot succeed. This deterministic switch exercises the same unavailable branch without uninstalling packages or altering the host.
