# Explicit unit and conversion registry

This registry is deliberately closed. Symbols are case-sensitive and exact aliases win before prefix parsing. Unknown units are never guessed. Canonical dimension exponents use `time`, `temperature`, `length`, `amount`, and `mass`. Volume is `length^3`; amount concentration is `amount * length^-3`.

## Prefixes

Applicable atoms accept exactly `n=1e-9`, `µ=u=μ=1e-6`, `m=1e-3`, `c=1e-2`, `d=1e-1`, `da=1e1`, `h=1e2`, `k=1e3`, `M=1e6`, `G=1e9`, and `T=1e12`. Prefixes are not freely attached to affine temperatures or non-prefixable aliases. Exact `M` and prefixed forms such as `mM` and `µM` mean molar concentrations based on `mol/L`; the same algebraic prefix rule gives `MM` its explicit mega-molar meaning rather than an alias for milli-molar.

## Atoms

| Quantity | Registered symbols and aliases | Linear scale to canonical dimensional realization |
|---|---|---|
| Temperature | `K` | `1 K` |
| Celsius | `°C`, `℃`, `degC`, `Celsius`, `celsius` | `K = °C + 273.15` (affine) |
| Fahrenheit | `°F`, `℉`, `degF`, `Fahrenheit` | `K = °F * (5/9) + 459.67*(5/9)` (affine) |
| Time | `s`, `sec`, `second(s)`; prefixable | `s` |
| Time | `min`, `minute(s)` | `60 s` |
| Time | `h`, `hr`, `hour(s)` | `3600 s` |
| Time | `day`, `d` | `86400 s` |
| Pressure | `Pa`; prefixable | `mass length^-1 time^-2` |
| Pressure | `bar` (prefixable, including `mbar`), `atm`, `mmHg`, `Torr`, `torr`, `psi` | `100000`, `101325`, `133.322387415`, `133.322387415`, `133.322387415`, `6894.757293168 Pa`, respectively |
| Energy | `J`; prefixable | `mass length^2 time^-2` |
| Energy | `cal`, `kcal` | `4.184`, `4184 J` |
| Energy | `Wh` (prefixable, including `kWh`) | `3600 J` |
| Energy | `eV`; prefixable | exact `1.602176634e-19 J` |
| Length | `m`, `metre`, `meter`; prefixable | `m` |
| Volume | `L`, `l`, `litre`, `liter`; prefixable | `0.001 m^3` |
| Amount | `mol`; prefixable | `mol` |
| Molar concentration | `M` | `1000 mol/m^3` (exactly `mol/L`) |

Compound expressions can use multiplication, division, parentheses, integer powers and implicit products. Thus `mmol/L`, `µM`, `mol m^-3 s^-1`, `kJ/h`, `mL/min`, `L^-1`, and `m³` are typed expressions rather than special-case strings.

## Conversion equations

Every unit atom has a Decimal linear `scale` and `offset` such that:

```text
base = raw * source.scale + source.offset
```

For source `S` and target `T`, evaluated with Decimal precision 60 before display rounding:

```text
multiplier = S.scale / T.scale
shift = S.offset / T.scale
normalized_target_offset = T.offset / T.scale
target = raw * multiplier + shift - normalized_target_offset
```

For pure linear units, both offsets are zero. Celsius→Kelvin uses multiplier `1`, shift `273.15`, target offset `0`. The same target-scale normalization also makes reverse affine conversion correct (`100 °C → 212 °F`). Dimension vectors must be identical before arithmetic.

Interval endpoints independently undergo the same transformation. If `multiplier < 0`, transformed endpoints are reversed so the output remains low then high. The ledger records `interval_reversed_for_negative_multiplier`. The built-in physical registry has positive scales, while the conversion implementation and self-test explicitly cover this algebraic negative-scale boundary.

Uncertainty uses `uncertainty_target = uncertainty_source * abs(multiplier)`; offsets never enlarge an uncertainty. Raw uncertainty and converted uncertainty are both retained. Missing values never pass through either formula.

## Target precedence and automatic canonical targets

Explicit case target-unit rules are authoritative. Material defaults are lower priority. With no field rule, auto mode requires an embedded registered unit and uses a small safe canonical map: `K`, `s`, `Pa`, `J`, `m`, `m^3`, `mol`, `mol/m^3`, and `mol/m^3/s`. Other dimensions require an explicit target and otherwise enter review; a unit spelling is not improvised.
