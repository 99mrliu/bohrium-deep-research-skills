# Input schema and runtime

## Files

The default runtime paths are `/input/case.json`, `/input/task.md`, `/app/work`, and `/app/output/result.json`. Equivalent flags allow local runs without those mount points. The verifier creates both output directories and writes a partial result before attempting evaluation.

The case has this shape:

```json
{
  "case_id": "source-assigned-id",
  "metamorphic_properties": "authored_properties.json",
  "quantities": {"x": {"value": 2.5, "unit": "mm", "scale": 1.0, "source": {"locator": "paper DOI or URL#page=3,equation=2"}}},
  "reported_claims": [
    {
      "claim_id": "equation-2-result",
      "formula": "x / t",
      "reported": {"lower": 0.49, "upper": 0.51, "unit": "m/s", "scale": 1.0, "rounding": {"step": 0.01}},
      "tolerance": {"absolute": 0.001, "relative": 0.002},
      "source": {"locator": "paper DOI or URL#equation-2"}
    }
  ]
}
```

A property spec may instead be an inline `{"properties": [...], "fault_injections": [...]}` object or a property list. A string is resolved relative to `case.json`. The bundle never imports anything from another challenge bundle.

## Quantities and sourcing

- `value` must be a finite JSON number, not a string or Boolean. `scale` is another finite multiplier and defaults to 1. `unit` is a non-empty unit string; use `1` for dimensionless.
- The canonical evaluated number is `value * scale * unit_factor_to_SI`. Every resolved baseline input is printed with its raw value, scale, unit, conversion factor, canonical value, dimensions, and locator.
- Every baseline quantity and reported claim requires `source.locator` (or the equivalent top-level `source_locator`). This obligation is on the agent: a guessed value with a real-looking locator is not acceptable sourcing.
- C01/C03-style inputs may provide `mathml` or `value_mathml` instead of `value`. Supported numeric Presentation MathML includes `mn`, `mrow`, numeric operators, `msup`, `mfrac`, `msqrt`, and `mfenced`. The unit is still supplied explicitly and the locator is still mandatory. The MathML is converted to the same restricted AST language; XML DOCTYPE/ENTITY input is rejected.
- The tool does not browse and does not turn article text, variable names, or MathML identifiers into empirical values.
- C02-style absence of a formula, raw value, interval, unit, tolerance, or locator blocks recalculation with `insufficient_evidence`. Variables are not silently initialized to zero or any other value.

An input value legitimately observed as zero remains zero; only imputed missing values are forbidden. Unsupported offset units (for example Celsius conversions) and unknown atoms are errors rather than guessed conversions. Supported SI/common atoms and prefixes are listed in `scripts/quantity_core.py`.

## Safe formula language

Formulas use Python-like arithmetic but are interpreted by an AST visitor; Python `eval` and `exec` are not used. Allowed syntax is finite numeric constants, supplied variable names, `pi`, `e`, parentheses, unary `+`/`-`, binary `+ - * / **`, and these allowlisted functions:

- `sqrt`, `abs`, `exp`, `ln`, `log`, `log10`, `sin`, `cos`, `tan`, `min`, `max`

No attributes, imports, subscripting, comprehensions, lambdas, comparisons, assignments, or arbitrary calls are accepted. Evaluation includes dimensional checks: addition and subtraction require equal dimensions; transcendental functions require dimensionless arguments; a dimensioned base requires an integer exponent. Length, node-count, and exponent limits bound expression complexity.

## Reported values, intervals, and tolerances

Use either `reported.value` or both `reported.lower` and `reported.upper`, in `reported.unit`, optionally with `reported.scale`. All comparisons occur after explicit conversion to the reported unit.

Each claim must specify both:

- `tolerance.absolute`: additive tolerance in reported units;
- `tolerance.relative`: dimensionless coefficient multiplied by the largest absolute magnitude among relevant compared numbers.

Rounding is not hidden. Specify `reported.rounding` as one of:

- `{"absolute": 0.05}`;
- `{"step": 0.1}`, contributing `step/2`;
- `{"decimal_places": 2}`, contributing `0.005`.

Alternatively use `tolerance.rounding_absolute`. It defaults to zero only when no rounding object is provided. The report exposes every component, total tolerance, recomputed value, raw interval, expanded interval, signed residual, and residual to the interval.

The base source-claim data are always computed without any injected mutation. `source_claim_verdict` values are `compatible_within_tolerance`, `inconsistent_with_recomputed_value`, or `insufficient_evidence`.
