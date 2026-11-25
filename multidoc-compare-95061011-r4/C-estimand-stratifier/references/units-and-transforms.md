# Units and exact-transform policy

## Unit identity is not estimand identity

Units are one estimand dimension. They never compensate for different outcome constructs, metric definitions, materials, pollutants, methods, horizons, or budgets. In particular, `92%` absorbance reduction for one dye and `92%` concentration removal for another dye have the same display unit but different meanings.

The normalized `estimate.unit` must equal the record-level `unit` when the estimate is numeric. Fractions, percentages, and percentage points must not be silently interconverted. `scale` records interpretation such as `percentage points on closed interval [0,100]`.

## Whitelist

The deterministic implementation permits only these conversions and only for the `time` and `budget` fields:

| conversion | Exact definition | Implementation |
| --- | --- | --- |
| `min_to_h` | `1 min = 1/60 h` | Exact rational multiplication by `1/60` |
| `h_to_min` | `1 h = 60 min` | Exact rational multiplication by `60` |

The example uses `min_to_h` on Paper A's 90 min time and exposure budget, producing exactly 1.5 h and entering Paper C's stratum. Conversion is explicit in the operation request and applied only to an in-memory copy. Each audit row records estimand ID, field, exact definition, reason, before measurement, and after measurement.

A transformed result must be exactly representable as a finite JSON decimal. For example, 90 min becomes 1.5 h. If a rational result has a denominator with a prime factor other than 2 or 5 (for example 1 min = 1/60 h), the operation is blocked rather than rounded or approximated. This conservative representability check prevents silent numeric drift. An analyst can instead retain the original units and describe the records.

## No implicit transformations

- No unit conversion is chosen merely because two records differ.
- No approximate currency conversion, dose normalization, molecular-weight conversion, or percentage conversion is included.
- Conversion requests with a wrong source unit, duplicate target field, non-time/budget field, unknown measurement, missing reason, or unknown conversion name are blocked.
- Time and budget are separate fields: both must be converted when both differ only by units.
- After conversion, every stratum dimension must match for TRANSFORM or RANK to be allowed. A conversion cannot bridge different metrics or pollutants.
- Source evidence and normalized source records are never rewritten to the converted value; conversion is a separately audited analytic operation.

## Extending the policy

A future conversion needs a documented exact mathematical identity, a field/unit whitelist, rational arithmetic, representability checks, negative tests, and reference documentation. Do not introduce approximate factors or infer conversions from numerical coincidence.
