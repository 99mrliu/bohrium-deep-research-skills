# Numerical verification — SYNTHETIC

**Status:** `passed`
**Ledger:** `synthetic-methods-a-b-low-high-errors-v1`

Calculated values are `independently_calculated`; source values retain their own provenance. A derived comparison does not authenticate the original source.

## Source values and anchors

| Value | Number | Unit | Provenance | Row / column / condition | Quote check |
|---|---:|---|---|---|---|
| a_high_control | 40 | percent | author_reported | Method A / High control (%) / high temperature, control | matched/region_verified |
| a_high_treatment | 30 | percent | author_reported | Method A / High treatment (%) / high temperature, treatment | matched/region_verified |
| b_high_control | 20 | percent | author_reported | Method B / High control (%) / high temperature, control | matched/region_verified |
| b_high_treatment | 16 | percent | author_reported | Method B / High treatment (%) / high temperature, treatment | matched/region_verified |
| a_low_control | 12 | percent | author_reported | Method A / Low control (%) / low temperature, control | matched/region_verified |
| a_low_treatment | 9 | percent | author_reported | Method A / Low treatment (%) / low temperature, treatment | matched/region_verified |
| b_low_control | 8 | percent | author_reported | Method B / Low control (%) / low temperature, control | matched/region_verified |
| b_low_treatment | 6 | percent | author_reported | Method B / Low treatment (%) / low temperature, treatment | matched/region_verified |
| a_high_body_control | 40 | percent | author_reported | Method A body assertion / initial high-temperature error / high temperature, control | matched/region_verified |
| a_high_body_treatment | 30 | percent | author_reported | Method A body assertion / final high-temperature error / high temperature, treatment | matched/region_verified |
| figure_1_a_high_control | missing | percent | missing | Method A (referenced only) / High control (referenced only) / high temperature, control; original figure unavailable | not_applicable/not_applicable |

## Decimal calculations

| Check | Operation | Raw → rounded | Expected | Tolerance | Result | Formula |
|---|---|---:|---:|---|---|---|
| a_high_relative_reduction | percent_relative_change (reduction) | 25 → 25.00 percent | 25 | absolute 0.0000001 | matched | 100 * (40 - 30) / abs(40) = 25 |
| a_high_pp_reduction | percentage_point_difference (reduction) | 10 → 10.00 percentage_points | 10 | absolute 0.0000001 | matched | 40 - 30 = 10 |
| b_high_relative_reduction | percent_relative_change (reduction) | 20 → 20.00 percent | 20 | absolute 0.0000001 | matched | 100 * (20 - 16) / abs(20) = 20 |
| b_high_pp_reduction | percentage_point_difference (reduction) | 4 → 4.00 percentage_points | 4 | absolute 0.0000001 | matched | 20 - 16 = 4 |
| a_low_relative_reduction | percent_relative_change (reduction) | 25 → 25.00 percent | 25 | absolute 0.0000001 | matched | 100 * (12 - 9) / abs(12) = 25 |
| a_low_pp_reduction | percentage_point_difference (reduction) | 3 → 3.00 percentage_points | 3 | absolute 0.0000001 | matched | 12 - 9 = 3 |
| b_low_relative_reduction | percent_relative_change (reduction) | 25 → 25.00 percent | 25 | absolute 0.0000001 | matched | 100 * (8 - 6) / abs(8) = 25 |
| b_low_pp_reduction | percentage_point_difference (reduction) | 2 → 2.00 percentage_points | 2 | absolute 0.0000001 | matched | 8 - 6 = 2 |
| a_high_final_initial_ratio | ratio (signed) | 0.75 → 0.75 dimensionless | 0.75 | absolute 0.0000001 | matched | 30 / 40 = 0.75 |
| a_high_signed_difference | difference (signed) | -10 → -10.00 percent | -10 | absolute 0.0000001 | matched | 30 - 40 = -10 |
| low_control_arithmetic_sum | sum (signed) | 20 → 20.00 percent | 20 | absolute 0.0000001 | matched | 12 + 8 = 20 |
| low_control_arithmetic_product | product (signed) | 96 → 96.00 percent * percent | 96 | absolute 0.0000001 | matched | 12 * 8 = 96 |
| high_control_arithmetic_division | division (signed) | 2 → 2.00 dimensionless | 2 | absolute 0.0000001 | matched | 40 / 20 = 2 |

## Input anchors

### a_high_relative_reduction
- `initial` (a_high_control): synthetic page 1, Table 1; row `Method A`; column `High control (%)`; condition `high temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `final` (a_high_treatment): synthetic page 1, Table 1; row `Method A`; column `High treatment (%)`; condition `high temperature, treatment`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
### a_high_pp_reduction
- `initial` (a_high_control): synthetic page 1, Table 1; row `Method A`; column `High control (%)`; condition `high temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `final` (a_high_treatment): synthetic page 1, Table 1; row `Method A`; column `High treatment (%)`; condition `high temperature, treatment`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
### b_high_relative_reduction
- `initial` (b_high_control): synthetic page 1, Table 1; row `Method B`; column `High control (%)`; condition `high temperature, control`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
- `final` (b_high_treatment): synthetic page 1, Table 1; row `Method B`; column `High treatment (%)`; condition `high temperature, treatment`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
### b_high_pp_reduction
- `initial` (b_high_control): synthetic page 1, Table 1; row `Method B`; column `High control (%)`; condition `high temperature, control`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
- `final` (b_high_treatment): synthetic page 1, Table 1; row `Method B`; column `High treatment (%)`; condition `high temperature, treatment`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
### a_low_relative_reduction
- `initial` (a_low_control): synthetic page 1, Table 1; row `Method A`; column `Low control (%)`; condition `low temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `final` (a_low_treatment): synthetic page 1, Table 1; row `Method A`; column `Low treatment (%)`; condition `low temperature, treatment`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
### a_low_pp_reduction
- `initial` (a_low_control): synthetic page 1, Table 1; row `Method A`; column `Low control (%)`; condition `low temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `final` (a_low_treatment): synthetic page 1, Table 1; row `Method A`; column `Low treatment (%)`; condition `low temperature, treatment`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
### b_low_relative_reduction
- `initial` (b_low_control): synthetic page 1, Table 1; row `Method B`; column `Low control (%)`; condition `low temperature, control`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
- `final` (b_low_treatment): synthetic page 1, Table 1; row `Method B`; column `Low treatment (%)`; condition `low temperature, treatment`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
### b_low_pp_reduction
- `initial` (b_low_control): synthetic page 1, Table 1; row `Method B`; column `Low control (%)`; condition `low temperature, control`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
- `final` (b_low_treatment): synthetic page 1, Table 1; row `Method B`; column `Low treatment (%)`; condition `low temperature, treatment`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
### a_high_final_initial_ratio
- `initial` (a_high_control): synthetic page 1, Table 1; row `Method A`; column `High control (%)`; condition `high temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `final` (a_high_treatment): synthetic page 1, Table 1; row `Method A`; column `High treatment (%)`; condition `high temperature, treatment`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
### a_high_signed_difference
- `initial` (a_high_control): synthetic page 1, Table 1; row `Method A`; column `High control (%)`; condition `high temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `final` (a_high_treatment): synthetic page 1, Table 1; row `Method A`; column `High treatment (%)`; condition `high temperature, treatment`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
### low_control_arithmetic_sum
- `method_a` (a_low_control): synthetic page 1, Table 1; row `Method A`; column `Low control (%)`; condition `low temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `method_b` (b_low_control): synthetic page 1, Table 1; row `Method B`; column `Low control (%)`; condition `low temperature, control`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
### low_control_arithmetic_product
- `method_a` (a_low_control): synthetic page 1, Table 1; row `Method A`; column `Low control (%)`; condition `low temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `method_b` (b_low_control): synthetic page 1, Table 1; row `Method B`; column `Low control (%)`; condition `low temperature, control`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.
### high_control_arithmetic_division
- `numerator` (a_high_control): synthetic page 1, Table 1; row `Method A`; column `High control (%)`; condition `high temperature, control`; unit `percent`; region `[419:450]`; quote: “| Method A | 12 | 9 | 40 | 30 |”; quote/locator check `matched/region_verified`.
- `denominator` (b_high_control): synthetic page 1, Table 1; row `Method B`; column `High control (%)`; condition `high temperature, control`; unit `percent`; region `[451:481]`; quote: “| Method B | 8 | 6 | 20 | 16 |”; quote/locator check `matched/region_verified`.

## Reconciliation

- `body_table_a_high_control`: **consistent** — Body and Table 1 both report 40 percent under the same high/control condition. Values: ['40', '40'].
- `body_table_a_high_treatment`: **consistent** — Body and Table 1 both report 30 percent under the same high/treatment condition. Values: ['30', '30'].
- `figure_table_a_high_control`: **not_checked** — Original Figure 1 is unavailable; no table/figure agreement or conflict can be inferred. Values: ['40', None].

## Visual comparison

```json
{
  "status": "derived_created",
  "derived_path": "comparison.svg",
  "original_render": {
    "status": "missing",
    "path": null
  },
  "original_crop": {
    "status": "missing",
    "path": null
  },
  "original_review": {
    "status": "missing",
    "checked_values": [],
    "note": "No original PDF/figure exists in this synthetic example. The SVG is derived from source tuples and is not evidence of original correctness."
  },
  "claim": "Derived plot of extracted values only; no correctness claim follows without original-render review."
}
```

## Limitations and uncertainty

- SYNTHETIC: the same eight fictional specimens were measured repeatedly; control/treatment measurements are correlated, not independent biological replicates.
- Original Figure 1 is missing; the derived comparison has not been checked against an original rendered figure.
- No dispersion or confidence interval is reported; none is calculated or invented.
- No OCR was needed for the UTF-8 synthetic text; real OCR may confuse decimal points, signs, digits, units, and columns.
- Inputs are displayed integers; arithmetic output precision does not establish measurement significant figures.
- Product and sum records exercise the engine only and are not pooled scientific endpoints.
- Decimal arithmetic checks formulas, not measurement quality or statistical independence.
- OCR, source rounding, significant figures, unit conversion, and original-image legibility can limit extraction.
- No confidence intervals, significance tests, or independence assumptions are generated.
