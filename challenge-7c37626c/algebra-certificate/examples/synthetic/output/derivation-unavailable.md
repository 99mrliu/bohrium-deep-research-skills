# Algebraic derivation certificate

**Overall:** `unavailable`  
**SymPy available:** `False`  
**Numeric sampling can falsify only; it is never a proof.**

Unavailable dependency: `simulated by --simulate-no-sympy`

## Paper-explicit transitions

### E1-valid-expansion: `undetermined`

- Operation: `expand`
- Source locator: synthetic derivation fixture E1 (not a paper locator)
- Dependencies: `[]`
- Required: `True`
- LHS/source: `(x + 1)**2`
- RHS/target: `x**2 + 2*x + 1`
- Justification: Expand the square and preserve addition over the real numbers.
- Declared assumptions: `['x real']`
- Domain declarations: `[]`
- Explanation: SymPy unavailable; no mathematical check attempted: simulated by --simulate-no-sympy

## Reader-reconstructed transitions

### C2-invalid-cancellation-at-zero: `undetermined`

- Operation: `cancel`
- Source locator: synthetic derivation fixture C2 (deliberate invalid step)
- Dependencies: `['E1-valid-expansion']`
- Required: `True`
- LHS/source: `x**2/x`
- RHS/target: `x`
- Justification: Deliberately invalid reader step: cancel x without assuming x != 0.
- Declared assumptions: `['x real']`
- Domain declarations: `[]`
- Explanation: SymPy unavailable; no mathematical check attempted: simulated by --simulate-no-sympy

### L3-invalid-real-log-power: `undetermined`

- Operation: `log_rule`
- Source locator: synthetic derivation fixture L3 (deliberate invalid step)
- Dependencies: `[]`
- Required: `True`
- LHS/source: `log(x**2)`
- RHS/target: `2*log(x)`
- Justification: Deliberately invalid reader step over all real x: the logarithm-power rewrite needs x > 0 for this target.
- Declared assumptions: `['x real']`
- Domain declarations: `[]`
- Explanation: SymPy unavailable; no mathematical check attempted: simulated by --simulate-no-sympy

## Unclassified transitions

None.
