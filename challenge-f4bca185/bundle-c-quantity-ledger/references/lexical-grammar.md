# Lexical grammar for numeric literals (quantity-ledger)

Applies to `scripts/quantity_ledger.py` v1.0.0. All parsing is `decimal.Decimal`
based; a literal is either parsed exactly as written or rejected to review —
never guessed.

## 0. Preprocessing

1. Unicode NFKC normalization (fullwidth digits → ASCII, superscripts → digits,
   `µ` → `μ`, thin space U+2009 / narrow no-break space U+202F / NBSP → space).
2. Mathematical minus U+2212 → ASCII `-`. **En dash `–`, em dash `—`, tilde
   `~` are preserved**: they are range separators, not signs.
3. The replacement character `�` aborts parsing with `encoding_replacement_char`.

## 1. Scalar grammar

```
number   := sign? mantissa exponent?
sign     := "+" | "-"
mantissa := digits grouping* (decsep digits+)? | decsep digits+
exponent := ("e" | "E") sign? digits
          | ("×" | "x") "10" "^"? sign? digits
```

- `digits grouping*`: integer part may contain **space groups of exactly 3**
  (`1 234 567`). Irregular grouping is rejected (`malformed_number`).
- Decimal separator rules (comma vs dot):
  - both present → the **rightmost** is the decimal separator, the other is a
    thousands separator (`1.234,56` → 1234.56; `1,234.56` → 1234.56);
  - only dot → dot decimal;
  - one comma with ≠3 digits after → decimal comma (`1,25` → 1.25);
  - one comma with exactly 3 digits after and a nonzero head → **ambiguous**
    (`1,234`) → review, not parsed;
  - multiple commas → valid only as strict 3-digit thousands groups.
- Significant figures of the mantissa are recorded in `sig_figs`.

## 2. Symmetric uncertainty (checked before ranges)

- `value ± unc`, `value +/- unc`, `value +- unc` → kind `symmetric`;
  uncertainty stays a **separate field**; derived bounds
  (`std_unc_low/high_derived = value ∓/± unc`) are explicitly flagged as
  derived. The `±` form is never rewritten as a range.
- `value(digits)` (parenthesis notation, e.g. `1.23(5)` → 1.23 ± 0.05) is
  supported; the digits scale with the last decimal place of the mantissa.

## 3. Ranges

- Explicit separators: en dash `–`, em dash `—`, `~`, `..`/`...`, `to`
  (`1.2–2.3`, `1.2 to 2.3`, `1.2~2.3`).
- A bare ASCII `-` is a range separator **only** when the whole string
  fullmatches `number - number`; the matcher backtracks over exponents, so
  `1e-3-2e-3` is the range [1e-3, 2e-3] while `-3` inside an exponent is never
  mistaken for a range split. Signed bounds (`-5–-2`) work.
- Parsed ranges keep `low`/`high` verbatim order; `low > high` yields anomaly
  `invalid_range_order`. Midpoints exist only as `std_midpoint_derived`.

## 4. Unit expressions (after the numeric part)

```
unit   := term ((space | "*" | "·" | "/") term)*
term   := symbol (("^" | "**")? signedint | signedint)?
```

- Implicit multiplication by whitespace: `mg L^-1`, `J mol-1 K-1`.
- `/` negates the exponent of the **next** term only: `kg/m^3`, `mg/L`.
- Superscript forms normalize through NFKC: `m²` → `m2` ≡ `m^2`.
- SI prefixes apply only to units flagged `prefixable` (longest prefix match,
  full symbol match wins: `min` ≠ milli-in, `mm` = milli-m).
- Affine units (`°C`, `°F`) must stand alone: any composition or exponent is
  `affine_in_composite`. Offsets apply to absolute values; uncertainties and
  temperature differences are scaled by the multiplier only.
- Ambiguous symbols (`C`, `ppt`) are rejected with `ambiguous_unit`.

## 5. Failure modes (all routed to anomalies + review)

| code | trigger |
|---|---|
| `missing_value` | empty value cell |
| `malformed_number` | token violates the grammar (`12..3`, `abc`) |
| `ambiguous_decimal_comma` | `1,234` etc. |
| `unknown_unit` | symbol/expression not in `units.json` (`qu`, `m//s`) |
| `ambiguous_unit` | `C`, `ppt` |
| `affine_in_composite` | `°C/kg`, `K^-1 °C` |
| `incompatible_target_unit` | dimensions differ from target (`target_units` misuse) |
| `encoding_replacement_char` | `�` in the value |
| `invalid_range_order` | `low > high` |
| `negative_absolute_temperature` | converted absolute T < 0 K |
