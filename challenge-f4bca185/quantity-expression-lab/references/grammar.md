# Typed quantity grammar

## Pipeline

A stateful scanner emits tokens; it is not a single regular expression. Two recursive-descent parsers then build (1) a point, interval, or uncertainty quantity and (2) a unit product/quotient/power tree. Conversion occurs only after both source and target have equal symbolic dimension-exponent vectors.

Informative EBNF (whitespace is insignificant):

```text
quantity      = [approx] number [range number] [plusminus number] unit_expr ;
unit_expr     = unit_power { (mul | "/" | implicit_space) unit_power } ;
unit_power    = (atom | "(" unit_expr ")") [("^" | superscript) signed_integer] ;
number        = [sign] mantissa [("e" | "E") [sign] integer] ;
approx        = "~" | "≈" | "≃" | "∼" ;
range         = "-" | "−" | "–" | "—" | "to" ;   # after the first endpoint
plusminus     = "±" | "+/-" ;
mul           = "*" | "·" | "⋅" | "×" ;
```

The scanner treats `−` as a sign where a number is expected and as a range operator between endpoints. `–` and `—` are ranges in that position. Scientific `e` is consumed only when followed by an exponent integer, leaving `1 eV` and `1eV` usable. Superscript exponents such as `m³` and `m⁻³` are accepted. Plain `m-3` is accepted only as a unit exponent, not as a quantity range.

Examples:

```text
25 °C                         point
10–20 °C                      interval, low then high
−5–5 °C                       interval with a Unicode-minus first endpoint
2.50 ± 0.05 kJ                central value and uncertainty magnitude
≈1.2e3 ms                     approximate scientific-notation point
1 mmol L^-1 min^-1            prefixed compound concentration/time rate
```

The source raw lexeme is never discarded. Approximation is a flag, not a numeric uncertainty. Intervals and `±` cannot share one cell. Input intervals must be low then high. Negative uncertainty is rejected. An affine central temperature value receives its offset; its uncertainty magnitude receives only the absolute linear multiplier.

## Number regions and conservative ambiguity

An actual case can specify `number_region` (`en-US`, `de-DE`, `fr-FR`, and registered families), or explicit `decimal_separator` and `thousands_separator`/`group_separator`. Case values take precedence. Explicit conventions still require valid thousands groups: one to three leading digits, then groups of exactly three.

- `en-US`: decimal `.`, grouping `,`.
- `de-DE` and related families: decimal `,`, grouping `.`.
- `fr-FR` and related families: decimal `,`, non-breaking-space grouping.
- `decimal-dot`/`decimal-comma`: specify decimal without authorizing malformed grouping.

In `auto` mode, digits without separators and ordinary decimals are accepted. When both comma and dot occur, the rightmost is decimal only if the other forms valid groups. NBSP, thin-space, and apostrophe separators are grouping-only. A single separator followed by exactly three digits after a nonzero leading integer, such as `1,234` or `12.500`, is **ambiguous** and rejected. A leading zero (`0.125`) is decimal. This intentionally conservative rule avoids silently selecting a locale. The example `1,234` is `1234` under `en-US` and `1.234` under `de-DE`; neither reading is guessed in auto mode.

Regular ASCII spaces are not accepted as intra-token thousands separators. Mixed grouping marks, repeated decimals, malformed exponents, excessive expressions, unexpected characters, and missing units after auto-detection are rejected or skipped according to the explicit/auto-field rules in `SKILL.md`.

## Unit-tree algebra

Multiplication adds dimension exponents, division subtracts them, and an integer power multiplies every exponent. Affine offset units cannot appear inside compounds or take powers other than one. Unknown atoms, fractional exponents, empty units, zero exponents, mismatched dimensions, and unclosed parentheses are reviewable errors. The parser never maps a similar-looking unknown unit to a registered one.

A numeric cell without an embedded unit is processed only when its explicit field specification gives `source_unit`/`unit_hint` or a `unit_field`. Automatic field mode ignores a plain numeric string rather than inventing a unit.
