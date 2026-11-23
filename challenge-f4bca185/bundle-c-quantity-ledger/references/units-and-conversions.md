# Units & conversion table (quantity-ledger)

Human-readable companion of `references/units.json` (the machine-readable
source of truth). `base = raw × factor + offset`; the ledger records
`multiplier = src_factor / tgt_factor` and `offset = (src_offset − tgt_offset) /
tgt_factor`, applied as `std = raw × multiplier + offset` with Decimal
arithmetic at 80-digit guard precision. No significant-figure rounding is
applied; any inexact Decimal step sets `rounded_inexact=true` in the ledger.

## Exact definitions (is_exact = true)

| unit | factor to SI base | notes |
|---|---|---|
| L | 0.001 m³ | litre |
| bar | 100000 Pa | 10⁵ Pa |
| atm | 101325 Pa | standard atmosphere |
| Torr | 101325/760 Pa | rational; decimal expansion is inexact → ledger flag |
| min / h / d / wk | 60 / 3600 / 86400 / 604800 s | |
| yr (Julian) | 31557600 s | 365.25 d; calendar years are not fixed durations |
| eV | 1.602176634e-19 J | exact since the 2019 SI |
| cal (thermochemical) | 4.184 J | use `cal` / `cal_th` |
| cal_IT | 4.1868 J | International Table calorie — a *different* definition |
| kcal_IT | 4186.8 J | |
| Wh | 3600 J | |
| %, ‰, ppm, ppb, pptn, ppth | 1e-2, 1e-3, 1e-6, 1e-9, 1e-12, 1e-3 (dimensionless) | ratios only |
| °C | K = °C × 1 + 273.15 | affine; differences ΔT are offset-free |
| °F | K = °F × 5/9 + 2298.35/9 | affine; i.e. (°F + 459.67) × 5/9 |

## Conventional / approximate definitions (is_exact = false)

| unit | factor | notes |
|---|---|---|
| mmHg | 133.322387415 Pa | conventional value |
| inHg | 3386.389 Pa | conventional value |
| psi | 6894.757293168 Pa | truncated decimal of the exact lbf/in² definition |
| Hartree (Eh) | 4.3597447222071e-18 J | CODATA 2018, rounded |

## Ambiguous symbols (never auto-converted)

- `C`: coulomb vs degrees Celsius → review. Use `°C`/`degC` for temperature.
- `ppt`: parts-per-thousand vs parts-per-trillion → review. Use `ppth`/`pptn`.

## Default targets

SI-coherent: m, kg, s, K, mol, m³, Pa, N, J, W, Hz, A s (charge), V,
`mol m^-3`, `kg m^-3`, `J mol^-1`, `J mol^-1 K^-1`, dimensionless `1`.
Per-case overrides: `{"target_units": {"<metric>": "<unit>", "*": "<unit>"}}`
in the case JSON; incompatible targets raise `incompatible_target_unit`.

## Composite units

Parsed as products of power terms: `mg L^-1` = 1e-6 kg / 1e-3 m³ → factor
1e-3 kg m⁻³; `kg/m^3` = kg m⁻³; `mol L−1` = 1000 mol m⁻³; `J mol−1 K−1` =
J mol⁻¹ K⁻¹. The ledger's `component_rules` list every unit/prefix rule id
(`U.mg|P.milli`, `U.L`, `U.power^-1`…) plus `UC.affine_linear`.

## Precision policy (binding)

1. All arithmetic in `decimal.Decimal`, guard precision 80; raw literals are
   kept untouched in every output.
2. No significant-figure rounding. Input significant figures are reported
   (`sig_figs`) but never enforced.
3. If a step is inexact (Torr division, negative powers of non-terminating
   factors), the value is the 80-digit-context result and
   `rounded_inexact=true` says so — the digits are then an approximation, not
   an exact conversion.
4. Uncertainties keep their own column; symmetric ± is converted by scaling
   with |multiplier| only (offsets never apply to differences).
5. Derived values (range midpoints, ± bounds) live only in `*_derived` columns.
