# Estimands, strata, and operation gates

## 1. The comparison unit is an estimand

An estimand record is an evidence-backed normalization of:

1. **outcome and metric definition**: the construct and the exact measurement definition, not just a metric label;
2. **population / material / pollutant**: what was studied and which substance or target was measured;
3. **intervention / method**: the treatment, measurement intervention, or method;
4. **condition / budget**: protocol conditions plus the relevant resource, dose, exposure, cost, mass, or time budget;
5. **time / horizon**: when or over what interval the outcome is defined;
6. **unit / scale**: reported unit and numerical interpretation, including whether values are fractions, percentage points, concentrations, or other scales.

The record also carries `task_id`, a numeric or `not_reported` `estimate`, a qualitative `direction`, and exact evidence. The stratum key is the canonical JSON of `task_id` and all six estimand dimensions. Numeric measurement values are canonicalized as decimal strings, object keys are sorted, and the displayed fingerprint is SHA-256 of the UTF-8 canonical key. Observed estimate values are deliberately **not** part of the key.

Semantic normalization is agent work. It must not erase meaningful distinctions merely to make strata match. Identical labels or identical percent units are not enough: the metric definition, material, pollutant, and all other dimensions still matter.

## 2. The intended operation determines comparability

| Operation | Permission rule | Required output behavior |
| --- | --- | --- |
| **DESCRIBE** | Allowed after source/schema validation, even when estimands differ. | Show side-by-side cells, all documents, exact evidence, mismatches, and `not_reported`; do not imply quantitative synthesis. |
| **DIRECTION** | Requires a reported qualitative direction for every selected record and explicit request caveats. Unlike estimands may be described qualitatively. | State directions only with caveats. Do not rank effect sizes or silently repair unknown conditions/budgets. |
| **RANK** | Requires compatible known data and the same estimand stratum after any explicitly requested exact transforms, plus compatible estimate units/scales. | Emit gate and rationale. Unknown values are blocked. A percent sign never overrides a different metric or pollutant. |
| **TRANSFORM** | Requires at least one whitelisted exact conversion, a reason, and post-transform stratum compatibility. Unknown values and unapproved conversions are blocked. | Preserve before/after values, units, exact definition, reason, and target record/field. Source records remain unchanged. |
| **POOL** | Must first satisfy the quantitative stratum/scale checks, and separately prove strong exchangeability. | Gate only. Never automatically pool, calculate a pooled effect, or invent heterogeneity statistics. |

For POOL, `design_compatibility`, `independence_or_overlap`, and `methodological_exchangeability` must each be explicitly `true`, with a substantive `justification`. The deterministic script checks presence and consistency; it cannot prove those substantive assertions. Tiny paper sets receive a warning because numerical similarity is not exchangeability. Usually, do not pool a tiny heterogeneous paper set even if the measurements share a unit.

## 3. Mismatches and unknowns are operation-specific

- A mismatch in one dimension blocks RANK and quantitative POOL for that joint stratum, but does **not** prohibit DESCRIBE.
- Equal `%` units and equal values do not collapse different metric meanings, pollutants, datasets, or dyes into one stratum.
- Any unknown core estimand dimension, estimate value, or estimate unit blocks RANK, TRANSFORM, and POOL. Unknowns are rendered rather than imputed.
- DIRECTION can remain allowed with an unknown budget only when a direction is actually reported and caveats are explicit.
- An omitted optional mild moderator need not make the response partial. Optional `moderators` are not part of the core stratum key. If the task makes such a moderator essential, the agent should represent it in `condition`, making its comparability consequence explicit.
- `noncomparable` is a legitimate analytic conclusion, not a work-completion failure.

## 4. Status is about completion, not agreement

`success` means every document was read, every requested gate was evaluated, evidence was preserved, and every recognized output-contract field was addressed. It may coexist with blocked RANK/POOL and explicit noncomparability. `partial` is reserved for incomplete work: an asserted completion flag is false or a contract field cannot be mapped without invention. Blocked operations alone never change `success` to `partial`.

Normal mode writes blocked decisions with honest status. `--strict-operations` intentionally fails on any blocked decision and is for negative validation, not the normal comparison workflow.

## 5. What the deterministic script does not decide

It does not read scientific meaning into free text, assume missing values, invent moderators, assess heterogeneity, run meta-analysis, or turn semantically different measures into a common currency. The agent supplies normalized records, exact evidence, and intended operations; the script validates, stratifies, converts only as requested, and gates.
