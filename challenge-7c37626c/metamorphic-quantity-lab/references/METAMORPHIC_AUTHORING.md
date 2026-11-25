# Authoring independent metamorphic checks

The runtime does not generate, infer, or repair properties. If no property is supplied, a compatible claim remains partial. Every property must have a unique `property_id`, a `kind`, `source.locator` identifying the authored spec, an `independence_statement`, and explicit absolute and relative tolerances. Scenario values should include `value`, `unit`, `scale`, and their authored source locators.

An invariant is independent only if it is not algebraically derived from the claimed result. Prefer symmetries, conservation laws, dimensional relations, externally stated bounds, orderings, or limiting behavior. Repeating the same RHS under a different name is a duplicate computation, not an independent invariant. A passing duplicate must not be described as corroboration.

## `scale_invariance`

```json
{
  "property_id": "common-scale-cancellation",
  "kind": "scale_invariance",
  "formula": "a / b",
  "scale_variable": "a",
  "scale_variables": ["a", "b"],
  "multipliers": [0.5, 2.0],
  "output_unit": "1",
  "tolerance": {"absolute": 1e-12, "relative": 1e-12, "rounding_absolute": 0},
  "source": {"locator": "authored-spec#common-scale-cancellation"},
  "independence_statement": "Common scaling cancels in this separately defined ratio; no reported numeric result was used to define it."
}
```

Use `scale_variables` for common rescaling, or the single `scale_variable` for a one-variable transformation. Each comparison reports baseline, transformed value, multiplier, residual, and tolerance. Do not call a relation scale-invariant just because it was observed to be numerically unchanged once.

## `monotonic_direction_over_sweep`

Supply `formula`, `sweep_variable`, at least two complete quantity objects in `sweep_values`, `output_unit`, and `expected_direction`: `strictly_increasing`, `strictly_decreasing`, `nondecreasing`, or `nonincreasing`. Strict means the step exceeds the explicit tolerance, not merely `>` at floating-point noise level. Non-strict checks use the equivalent tolerance-aware boundary.

Set `"plot": true` to request a runtime PNG. The verifier always has JSON/Markdown output and writes the sweep CSV even without matplotlib. If matplotlib is unavailable, it records a warning and omits PNG without failing the numerical check. Plot files go only to the runtime work directory.

## `limit`

A limit property supplies `formula`, `limit_variable`, a finite ordered `approach_values` list, an independently authored `expected` quantity, and tolerances. The final point must agree with the expectation; all points and residuals are reported. Finite calculations are only a limiting-case check, **not a proof of a mathematical limit** or of continuity.

## `expected_transformed_relation`

```json
{
  "property_id": "linearity-under-doubling",
  "kind": "expected_transformed_relation",
  "mutations": [{"target": "mass", "kind": "scale", "factor": 2}],
  "left_formula": "0.5 * mass * velocity**2",
  "right_formula": "mass * velocity**2",
  "output_unit": "J",
  "tolerance": {"absolute": 1e-12, "relative": 1e-12, "rounding_absolute": 0},
  "source": {"locator": "authored-spec#linearity-under-doubling"},
  "independence_statement": "This separate linearity check was authored from the stated formula family, not from the reported interval."
}
```

The left formula is evaluated after listed mutations; the right formula uses the unmutated baseline. They agree only within the recorded tolerance. Supported ordinary mutation kinds are `scale`/`multiply` and `convert_value_and_unit`; unit relabeling is described below.

## Deliberate faults and prefix sensitivity

Place faults beside the properties:

```json
{
  "fault_id": "deliberate-prefix-defect",
  "kind": "dimensional_prefix_mutation",
  "target": "distance",
  "replacement_unit": "µm",
  "expect": "detected"
}
```

This replaces only the unit label while preserving raw value and scale. For example, relabeling `1 kg` as `1 g` changes canonical magnitude by 1000, `1 m/s` as `1 mm/s` by 1000, and `1 m/s` as `1 µm/s` by 1,000,000. ASCII `u` and `micro` prefixes are also supported. The returned `canonical_mutation_factor` makes this explicit.

A fault is detected only when a previously compatible source claim becomes inconsistent or a previously passed property fails. If there was no clean baseline transition, it is not counted as a successful detector. Fault outcomes and all mutated intermediates stay under `diagnostic_fault_injection_verdict`, with explicit diagnostic-only attribution. They never alter the unmutated `source_claim_verdict` and are never evidence against a paper or source.

`convert_value_and_unit` performs the valid conversion while preserving canonical quantity and is useful as a separate control. Do not describe deliberate mutations as properties of the original source.
