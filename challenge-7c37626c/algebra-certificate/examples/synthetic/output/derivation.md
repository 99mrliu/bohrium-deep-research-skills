# Algebraic derivation certificate

**Overall:** `falsified`  
**SymPy available:** `True`  
**Numeric sampling can falsify only; it is never a proof.**

## Paper-explicit transitions

### E1-valid-expansion: `symbolic_equal`

- Operation: `expand`
- Source locator: synthetic derivation fixture E1 (not a paper locator)
- Dependencies: `[]`
- Required: `True`
- LHS/source: `(x + 1)**2`
- RHS/target: `x**2 + 2*x + 1`
- Justification: Expand the square and preserve addition over the real numbers.
- Declared assumptions: `['x real']`
- Domain declarations: `[]`
- Explanation: SymPy proved lhs-rhs = 0 and all original-expression domain licenses hold. No numeric proof was used.
- Symbolic checks:
    - simplify(lhs-rhs) -> 0
- Sampling: `{'method': 'not needed after symbolic proof', 'assignments_tested': 0}`

## Reader-reconstructed transitions

### C2-invalid-cancellation-at-zero: `falsified`

- Operation: `cancel`
- Source locator: synthetic derivation fixture C2 (deliberate invalid step)
- Dependencies: `['E1-valid-expansion']`
- Required: `True`
- LHS/source: `x**2/x`
- RHS/target: `x`
- Justification: Deliberately invalid reader step: cancel x without assuming x != 0.
- Declared assumptions: `['x real']`
- Domain declarations: `[]`
- Explanation: Concrete assumption-respecting counterexample found; numeric sampling was used only to falsify.
- **Domain error:** division/negative power denominator (x) lacks a nonzero declaration
- Symbolic checks:
    - simplify(lhs-rhs) -> 0
- Sampling: `{'method': 'deterministic_assumption_respecting_rationals', 'assignments_tested': 1, 'assignments_with_undetermined_constraints': 0}`
- **Counterexample:** `{'assignment': {'x': '0'}, 'lhs_value': '0**2*zoo', 'rhs_value': '0', 'reason': 'exactly one side is defined: lhs=undefined or nonfinite; rhs=defined'}`

### L3-invalid-real-log-power: `falsified`

- Operation: `log_rule`
- Source locator: synthetic derivation fixture L3 (deliberate invalid step)
- Dependencies: `[]`
- Required: `True`
- LHS/source: `log(x**2)`
- RHS/target: `2*log(x)`
- Justification: Deliberately invalid reader step over all real x: the logarithm-power rewrite needs x > 0 for this target.
- Declared assumptions: `['x real']`
- Domain declarations: `[]`
- Explanation: Concrete assumption-respecting counterexample found; numeric sampling was used only to falsify.
- **Domain error:** real logarithm argument (x**2) lacks a positive declaration
- **Domain error:** real logarithm argument (x) lacks a positive declaration
- Symbolic checks:
    - simplify(lhs-rhs) -> -2*log(x) + log(x**2)
    - expand(lhs-rhs) -> -2*log(x) + log(x**2)
    - factor(lhs-rhs) -> -2*log(x) + log(x**2)
    - trigsimp(lhs-rhs) -> -2*log(x) + log(x**2)
    - powsimp(lhs-rhs) -> -2*log(x) + log(x**2)
- Sampling: `{'method': 'deterministic_assumption_respecting_rationals', 'assignments_tested': 2, 'assignments_with_undetermined_constraints': 0}`
- **Counterexample:** `{'assignment': {'x': '-1/2'}, 'lhs_value': '-2*log(2)', 'rhs_value': '-2*log(2) + 2*I*pi', 'reason': 'concrete values differ under the declared assumptions'}`

## Unclassified transitions

None.
