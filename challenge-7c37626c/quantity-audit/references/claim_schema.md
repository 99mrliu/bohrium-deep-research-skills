# Claim ledger schema (`/app/work/claims.json`)

One JSON object; `claims` is a list. Every claim re-derives one checkable
published number from the paper's own formula, symbols and values.

```json
{
  "claims": [
    {
      "claim_id": "unique-slug",
      "formula_latex": "D = \\frac{\\mu k_{\\mathrm{B}} T}{q}",
      "binding": {
        "mu": {"value": 4e-4, "unit": "cm^2 V^-1 s^-1",
               "source": "sec 'Model', 'zero-field mobility'"},
        "k_B": {"value": 8.617e-5, "unit": "eV/K",
                "source": "sec 'Model', Boltzmann constant"},
        "T":   {"value": 300, "unit": "K",
                "source": "sec 'Model', 'taken as T = 300 K'"},
        "q":   {"value": 1.602e-19, "unit": "C",
                "source": "sec 'Model', elementary charge"}
      },
      "reported": {"value": 1.03e-5, "unit": "cm^2 s^-1",
                   "source": "Table 1"},
      "tolerance_rel": 0.05
    }
  ]
}
```

## Binding rules

- Every symbol in the formula must appear in `binding`, under the name the
  parser produces: Greek commands become their names (`\mu` -> `mu`),
  subscripts merge into the name (`k_{\mathrm{B}}` -> `k_B`).
- Each entry needs `value`, `unit` and `source` (the exact sentence/table).
  `source` is evidence, not decoration: an audit row without it cannot be
  traced back.
- If the paper does not give the value, write
  `{"unknown": true, "sought_at": "where you looked"}` instead of a number.
  The claim becomes BLOCKED and the missing object is named.
- Units use ASCII spellings handled by the SI engine: `m cm mm um nm km s min
  h kg g A K C V J N W Pa ohm eV count`, compound forms like `cm^2 V^-1 s^-1`,
  `eV/K`, `(V cm^-1)^-1/2`. Unknown spellings BLOCK the claim — report the
  spelling rather than silently rewriting it.
- `q`, `e`, `k_B`, `k_B_J`, `c`, `h`, `N_A`, `m_e` are filled from CODATA
  automatically when unbound; anything else must be bound from the paper.

## Verdict vocabulary

| verdict | meaning |
|-|-|
| PASS | recomputed value reproduces the reported one within tolerance |
| MISMATCH | dims match but values diverge beyond tolerance; check rounding, the binding values, or the paper's own arithmetic |
| DIM_MISMATCH | recomputed dimension disagrees with the reported unit — structural or unit error |
| BLOCKED | missing values/unknown units/unparseable constructs; missing objects named |
| UNPARSEABLE | LaTeX outside the parser subset; the parser error is recorded |
| PASS_COMPUTED_ONLY | recomputation done, nothing reported to compare |
