# Comparison operations

Case: `synthetic-estimand-case-001`
Completion status: **success**

Status reflects work completion, not whether every requested operation is allowed. A completed comparison can be `success` with blocked RANK/POOL operations. This script never performs meta-analysis or invents heterogeneity statistics.

## describe-all: DESCRIBE

Decision: **ALLOWED**

Estimands: `a-decolorization`, `b-adsorption`, `c-decolorization-hours`

Raw estimand comparability: **noncomparable**

Rationale: DESCRIBE permits unlike measures and unknown cells; no numeric synthesis is implied.

Blocking reasons: none.

Caveats:
- Side-by-side description retains unlike dimensions: budget, intervention, material, metric, outcome, pollutant, population, time
- Not-reported cells remain explicit: b-adsorption:budget.unit, b-adsorption:budget.value

Mismatching estimand dimensions after requested transforms: budget, intervention, material, metric, outcome, pollutant, population, time

## direction-a-b: DIRECTION

Decision: **ALLOWED**

Estimands: `a-decolorization`, `b-adsorption`

Raw estimand comparability: **noncomparable**

Rationale: DIRECTION is gateable with explicit caveats and reported directions; effect sizes are not ranked.

Blocking reasons: none.

Caveats:
- A decrease is qualitative only: absorbance-based decolorization of Reactive Red 195 and adsorption-based removal of Methylene Blue have different meanings and must not be ranked by effect size.
- The unreported adsorbent-mass budget remains a limitation even for qualitative comparison.
- Directions are qualitative only across dimensions: budget, intervention, material, metric, outcome, pollutant, population
- Qualitative direction does not repair missing values: b-adsorption:budget.unit, b-adsorption:budget.value

Mismatching estimand dimensions after requested transforms: budget, intervention, material, metric, outcome, pollutant, population

Qualitative directions only (not effect-size ranks):

- `a-decolorization`: **decrease**
- `b-adsorption`: **decrease**

- Explicit request caveat: A decrease is qualitative only: absorbance-based decolorization of Reactive Red 195 and adsorption-based removal of Methylene Blue have different meanings and must not be ranked by effect size.
- Explicit request caveat: The unreported adsorbent-mass budget remains a limitation even for qualitative comparison.

## rank-a-b: RANK

Decision: **BLOCKED**

Estimands: `a-decolorization`, `b-adsorption`

Raw estimand comparability: **noncomparable**

Rationale: RANK requires one known estimand and compatible estimate scale after any requested exact transforms.

Blocking reasons:
- `ESTIMAND_MISMATCH:budget,intervention,material,metric,outcome,pollutant,population`
- `UNKNOWN:b-adsorption:budget.unit`
- `UNKNOWN:b-adsorption:budget.value`

Mismatching estimand dimensions after requested transforms: budget, intervention, material, metric, outcome, pollutant, population

## pool-a-b: POOL

Decision: **BLOCKED**

Estimands: `a-decolorization`, `b-adsorption`

Raw estimand comparability: **noncomparable**

Rationale: POOL is only a gate; no pooled estimate or heterogeneity statistic is calculated.

Blocking reasons:
- `ESTIMAND_MISMATCH:budget,intervention,material,metric,outcome,pollutant,population`
- `POOL_EXCHANGEABILITY_NOT_JUSTIFIED`
- `UNKNOWN:b-adsorption:budget.unit`
- `UNKNOWN:b-adsorption:budget.value`

Caveats:
- Tiny paper set: exchangeability is not inferred from numerical similarity; pooling is normally inappropriate.

Mismatching estimand dimensions after requested transforms: budget, intervention, material, metric, outcome, pollutant, population

Numeric synthesis: **not_performed**. Even an allowed POOL gate would require a separately specified analysis.

## transform-a-c: TRANSFORM

Decision: **ALLOWED**

Estimands: `a-decolorization`, `c-decolorization-hours`

Raw estimand comparability: **noncomparable**

Rationale: TRANSFORM permits only documented exact conversions and requires post-conversion stratum identity.

Blocking reasons: none.

Exact transform audit (in-memory copies; source records and quotes are unchanged):

| estimand_id | field | conversion | exact definition | before | after | reason |
| --- | --- | --- | --- | --- | --- | --- |
| a-decolorization | time | min_to_h | 1 min = 1/60 h (exact) | {"unit":"min","value":90} | {"unit":"h","value":1.5} | Convert the 90 min observation horizon to the common 1.5 h horizon using the exact definition 1 min = 1/60 h. |
| a-decolorization | budget | min_to_h | 1 min = 1/60 h (exact) | {"unit":"min","value":90} | {"unit":"h","value":1.5} | Convert the 90 min exposure budget to the common 1.5 h exposure budget using the exact definition 1 min = 1/60 h. |

## rank-a-c-after-transform: RANK

Decision: **ALLOWED**

Estimands: `a-decolorization`, `c-decolorization-hours`

Raw estimand comparability: **noncomparable**

Rationale: RANK requires one known estimand and compatible estimate scale after any requested exact transforms.

Blocking reasons: none.

Exact transform audit (in-memory copies; source records and quotes are unchanged):

| estimand_id | field | conversion | exact definition | before | after | reason |
| --- | --- | --- | --- | --- | --- | --- |
| a-decolorization | time | min_to_h | 1 min = 1/60 h (exact) | {"unit":"min","value":90} | {"unit":"h","value":1.5} | Match the observation horizon exactly before ranking. |
| a-decolorization | budget | min_to_h | 1 min = 1/60 h (exact) | {"unit":"min","value":90} | {"unit":"h","value":1.5} | Match the exposure budget exactly before ranking. |

## Minimal operation semantics

- **DESCRIBE**: side-by-side unlike measures and not-reported cells remain visible.
- **DIRECTION**: qualitative directions only, with explicit caveats; no ranking by effect size.
- **RANK**: one known estimand and one compatible scale after approved exact transforms.
- **TRANSFORM**: only exact, whitelisted, requested conversions with before/after audit.
- **POOL**: additionally requires explicit strong exchangeability; no automatic pooled estimate.
