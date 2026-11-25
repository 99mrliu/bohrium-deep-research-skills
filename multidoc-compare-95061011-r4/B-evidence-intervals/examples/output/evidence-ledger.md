# Evidence interval ledger

Only records in the validated section feed matrix and synthesis.

## Validated records (4)

### alpha-main-128

- Document: `fictional-alpha`; paragraph: `fictional-alpha-p0004`; page: `1`
- Claim: Aerogel A / methylene blue / adsorption_capacity = **128.0 mg/g**
- Budget: initial concentration 40 mg/L, adsorbent dose 1 g/L, contact time 120 min, temperature 298 K
- Evidence class/status: `direct` / `conflicted`; comparability: `noncomparable`
- Uncertainty: The main result and a later author note disagree without explanation; both are retained and neither is selected.

#### alpha-main-support (`support`)

Locator `fictional-alpha` / `fictional-alpha-p0004` / page 1 / characters 0:62 / SHA-256 `7735dd86e0923dbcb7af4fe4dcf9cace9a7bf5c48f340e689f8f2d6fa525844c`

> For Experiment A, the adsorption_capacity result was 128 mg/g.

#### alpha-main-context (`context`)

Locator `fictional-alpha` / `fictional-alpha-p0002` / page 1 / characters 0:174 / SHA-256 `31cc954e19bba89fe39feaca7b0f1fcc44dfe7bd7fc8af635a040b16ef3eae45`

> Experiment A uses material Aerogel A for pollutant methylene blue. The budget is initial concentration 40 mg/L, adsorbent dose 1 g/L, contact time 120 min, temperature 298 K.

#### alpha-main-definition (`definition`)

Locator `fictional-alpha` / `fictional-alpha-p0003` / page 1 / characters 0:137 / SHA-256 `9dd6e0d37220e4c1089ce4f07c8b605c5d95ce269a74048c0849dc499b48f9c5`

> Metric definition: adsorption_capacity means the retained pollutant mass divided by dry adsorbent mass, expressed in mg/g at equilibrium.

### alpha-note-132

- Document: `fictional-alpha`; paragraph: `fictional-alpha-p0005`; page: `1`
- Claim: Aerogel A / methylene blue / adsorption_capacity = **132.0 mg/g**
- Budget: initial concentration 40 mg/L, adsorbent dose 1 g/L, contact time 120 min, temperature 298 K
- Evidence class/status: `direct` / `conflicted`; comparability: `noncomparable`
- Uncertainty: The unexplained 132 mg/g note conflicts with the 128 mg/g main result and remains a separate conflicted record.

#### alpha-note-support (`support`)

Locator `fictional-alpha` / `fictional-alpha-p0005` / page 1 / characters 0:149 / SHA-256 `a264f1469059c51ed9205e6c0c27438bafef8e24081578c5cc0bb18b8a7ec2ae`

> A later author note for Experiment A revised adsorption_capacity to 132 mg/g using the same reported conditions; the note did not explain the change.

#### alpha-note-context (`context`)

Locator `fictional-alpha` / `fictional-alpha-p0002` / page 1 / characters 0:174 / SHA-256 `31cc954e19bba89fe39feaca7b0f1fcc44dfe7bd7fc8af635a040b16ef3eae45`

> Experiment A uses material Aerogel A for pollutant methylene blue. The budget is initial concentration 40 mg/L, adsorbent dose 1 g/L, contact time 120 min, temperature 298 K.

#### alpha-note-definition (`definition`)

Locator `fictional-alpha` / `fictional-alpha-p0003` / page 1 / characters 0:137 / SHA-256 `9dd6e0d37220e4c1089ce4f07c8b605c5d95ce269a74048c0849dc499b48f9c5`

> Metric definition: adsorption_capacity means the retained pollutant mass divided by dry adsorbent mass, expressed in mg/g at equilibrium.

### beta-derived-128

- Document: `fictional-beta`; paragraph: `fictional-beta-p0004`; page: `1`
- Claim: Membrane B / rhodamine B / adsorption_capacity = **128.0 mg/g**
- Budget: initial concentration 60 mg/L, solution volume 250 mL, contact time 90 min, temperature 298 K
- Evidence class/status: `derived` / `confirmed`; comparability: `noncomparable`
- Uncertainty: The value is a justified derived conversion, not a quoted capacity result; it remains noncomparable for pooling with different dyes and budgets.

#### beta-support (`support`)

Locator `fictional-beta` / `fictional-beta-p0004` / page 1 / characters 0:146 / SHA-256 `4ff81783e1fd5bba2c08d472be395f8a323817c1a94297a623a912f568816c85`

> For Experiment B, the recovered solid retained 512 mg rhodamine B and the dry adsorbent mass was 4 g. No capacity value was printed in the source.

#### beta-context (`context`)

Locator `fictional-beta` / `fictional-beta-p0002` / page 1 / characters 0:173 / SHA-256 `9e82d98c95edc51bc640c1ddd53303ba5e9f49c7c2d142171a52158ecbbbc9f3`

> Experiment B uses material Membrane B for pollutant rhodamine B. The budget is initial concentration 60 mg/L, solution volume 250 mL, contact time 90 min, temperature 298 K.

#### beta-definition (`definition`)

Locator `fictional-beta` / `fictional-beta-p0003` / page 1 / characters 0:165 / SHA-256 `93ae05879dedd0ea7836106561c8338ec7e0b42b9cf38b5e84aca5a2b3dbad78`

> Metric definition: adsorption_capacity is retained_mass / adsorbent_mass. The requested result unit is mg/g; retained_mass is measured in mg and adsorbent_mass in g.

Derivation (independently evaluated):

```json
{
  "formula": "retained_mass / adsorbent_mass",
  "justification": "Both sourced operands describe Experiment B; mg divided by g gives the requested mg/g unit without changing the experimental budget.",
  "operands": [
    {
      "name": "retained_mass",
      "source_span_id": "beta-support",
      "unit": "mg",
      "value": 512.0,
      "value_literal": "512"
    },
    {
      "name": "adsorbent_mass",
      "source_span_id": "beta-support",
      "unit": "g",
      "value": 4.0,
      "value_literal": "4"
    }
  ],
  "result_unit": "mg/g"
}
```

### gamma-capacity-absent

- Document: `fictional-gamma`; paragraph: `not_reported`; page: `not_reported`
- Claim: Granule C / methyl orange / adsorption_capacity = **not_reported mg/g**
- Budget: initial concentration 50 mg/L, adsorbent dose 2 g/L, contact time 60 min, temperature 298 K
- Evidence class/status: `absent` / `not_reported`; comparability: `noncomparable`
- Uncertainty: not_reported applies only to this complete indexed fictional document; no source paragraph or quotation is fabricated for an absent value.

Negative-evidence search scope (no quotation):

```json
{
  "corpus_sha256": "86ed03517c98c0280dd09b946489f3f8bf00f9a381ccede7c5acb772566bfbdf",
  "paragraph_ids": [
    "fictional-gamma-p0001",
    "fictional-gamma-p0002",
    "fictional-gamma-p0003"
  ],
  "queries": [
    "adsorption_capacity",
    "equilibrium capacity",
    "q_e",
    "mg/g",
    "result"
  ],
  "source_document_id": "fictional-gamma"
}
```

## Excluded records (0)

