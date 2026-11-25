# Assumption and declaration vocabulary

Put declarations in `assumptions` and/or `domain`; they are merged for that step. The preferred form is a JSON array of short strings:

```json
[
  "x real",
  "x > 0",
  "y nonzero",
  "n integer",
  "t >= 0",
  "z != 0"
]
```

A single string and an object such as `{"x": "real nonzero", "y": "positive"}` are also accepted. Object keys are symbol names. Within an object value, use words or semicolon-separated relations; in array/string form each relation must be its own array item.

## Property words

| Declaration | Meaning supplied to the checker |
|---|---|
| `x real` | `x ∈ ℝ` |
| `x positive` | `x > 0` (also implies real and nonzero) |
| `x negative` | `x < 0` (also implies real and nonzero) |
| `x nonnegative` | `x >= 0` (also implies real) |
| `x nonpositive` | `x <= 0` (also implies real) |
| `x nonzero` | `x != 0` |
| `x integer` | `x ∈ ℤ` (also implies real) |

Word synonyms `> 0`, `!= 0`, etc. are preferable when possible. An array item can contain multiple whitespace-separated property words (for example, `"x real nonzero"`). A relational declaration must be isolated as its own item, such as `"x > 0"`, not combined with prose.

Accepted comparison forms are `>`, `>=`, `<`, `<=`, `=`, `==`, and `!=`. Both `x > 0` and `0 < x` are accepted. Expressions in comparisons use the same safe arithmetic/function grammar as derivation expressions. Write powers as `**` or `^`; multiplication must be explicit (`2*x`, not `2x`).

## What licenses a transition

- **Division:** every nonconstant denominator baseline must be declared nonzero, or SymPy must establish nonzero from declared symbol assumptions. For example, `x real` alone does not license `1/x`; add `x != 0` or `x > 0`.
- **Cancellation:** all denominators in the original source and target must be licensed. A zero algebraic difference after automatic cancellation is insufficient: the checker inspects unevaluated original expressions. For a cancelled numerator factor, include it in `nonzero_factors` on the step, for example `"nonzero_factors": ["x-1"]`. The general denominator audit remains mandatory.
- **Real square root:** the radicand must be nonnegative. A positive declaration is stronger and is accepted.
- **Real logarithm:** the argument must be positive. `x real` and `x != 0` are not enough for `log(x)`, because negative real inputs leave the real domain.
- **Negative-integer power:** the base must be nonzero. For an even-denominator rational power, the base must be nonnegative. For other noninteger real powers in a real-valued derivation, declare the base positive unless the checker can establish an equivalent safe condition.
- **Combined expressions:** both `lhs` and `rhs` are audited. Licenses mentioned only in free-text justification do not count.

Constant denominators, roots, and logarithms are checked directly. A syntactically missing declaration may remain `missing_license` even where a human could prove a more subtle theorem; conservative incompleteness is intentional.

## Counterexample sampling

The checker proposes deterministic rational samples and values around constants appearing in declarations, then retains only assignments satisfying every parseable declaration. Boundary candidates include zero where allowed and can expose a cancelled denominator. This process can falsify but cannot establish an identity. Infinite-interval reasoning, quantifier elimination, and arbitrary expression solving are not claimed.

## Paper versus reader provenance

Assumptions explicitly printed in the paper should appear in `assumptions` with an exact locator in `source_locator` or `assumption_locator`. Side conditions added by the reader to repair a transition belong in `domain`, with `origin: "reader_reconstruction"`. Adding a missing premise may make a local check valid, but it does not prove that the paper originally stated or had that premise; keep this distinction visible in the answer.
