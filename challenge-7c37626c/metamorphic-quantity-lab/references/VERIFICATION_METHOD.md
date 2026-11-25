# Verification method and interpretation

This bundle is falsification-oriented. A single matching right-hand-side evaluation is only one observation. The workflow combines that observation with sourced intermediates, explicit uncertainty/rounding comparisons, and independently authored transformations that could fail.

For a recomputed scalar `r` and reported interval `[L, U]`, converted to the same unit, the raw residual is:

- zero when `L <= r <= U`;
- `L-r` when `r < L`;
- `r-U` when `r > U`.

The comparison tolerance is `absolute + relative*M + rounding_absolute`, where `M` is the largest relevant reported/recomputed magnitude. The residual must not exceed this total. A point value is represented as a zero-width interval. These definitions and all substituted components are retained in `analysis.json` and `report.md`.

A failed check can reveal an arithmetic, unit, scale, transcription, formula, or expectation discrepancy. It does not automatically identify which one is responsible. Investigate source locators and intermediate values before considering model error. Never widen a tolerance post hoc just to obtain agreement; document any source-stated uncertainty and its basis.

A compatible check is weaker still: **equality within tolerance does not validate a model, its assumptions, a physical mechanism, or a source**. Many wrong models can agree at one point. Likewise, a sweep can pass while a different scale or regime fails, and a finite limit sequence cannot prove a limit.

Injected faults test whether the verification apparatus can detect known defects. They are not findings about the unmutated claim. Keep their diagnosis separate even in prose: for example, “The unmutated source interval is compatible; the deliberately relabelled millimetre mutation was detected,” not “the paper has a millimetre error.”

Use these evidence boundaries:

1. Missing C02 raw values/formulas/units/locators means recalculation is blocked; preserve `partial` and `insufficient_evidence`.
2. No authored properties means no complete metamorphic verification, even when a claim recalculates exactly.
3. Property evaluation errors also keep the run partial; they are not passes or failures.
4. A clean baseline with failed properties may be complete verification with a falsifying discrepancy, but not successful validation.
5. Optional plotting never controls numerical status. JSON and Markdown are primary; CSV records sweep points.

The implementation is deliberately transparent rather than statistically comprehensive. It does not infer Bayesian posteriors, propagate arbitrary correlated uncertainty, prove symbolic equivalence, or establish that a proposed invariant is scientifically valid. Those judgments belong to the agent and must be stated as limitations.
