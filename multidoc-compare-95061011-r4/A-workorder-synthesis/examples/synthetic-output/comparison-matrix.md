# Comparison matrix

**SYNTHETIC MINIMAL EXAMPLE — NOT AN OFFICIAL CASE ANSWER**

Case: `SYNTHETIC-95061011-THREE-DOC-001`

## Document coverage

| In-scope source_document_id | Source text | Matrix cells |
|---|---|---:|
| SYN-A | corpus/syn-a.txt | 4 |
| SYN-B | corpus/syn-b.txt | 4 |
| SYN-C | corpus/syn-c.txt | 4 |

## Agent-authored evidence cells

| Question | Dimension | source_document_id | paragraph_id | State | Value | Units | Source span | Comparability metadata |
|---|---|---|---|---|---|---|---|---|
| q1 | protocol identity | SYN-A | SYN-A:p1 | reported | M-1 / D-1 / stirred batch / P-60 | not_applicable | Study A used material M-1 to remove dye D-1 in a stirred batch task under protocol P-60. | {} |
| q2 | 60-minute removal | SYN-A | SYN-A:p2 | reported | 70 | percent | At 60 minutes, removal was 70 percent under protocol P-60 | {"budget": "shared screening cap 600 USD","material": "M-1","metric": "removal_at_60_min","pollutant": "D-1","task": "stirred batch removal under protocol P-60","units": "percent"} |
| q3 | confirmation cost and shared cap | SYN-A | SYN-A:p3 | reported | {"confirmation_cost_usd": 240,"shared_cap_usd": 600} | USD | The confirmation run costs 240 USD against the shared 600 USD screening budget | {"units": "USD"} |
| q4 | replicate variance | SYN-A | SYN-A:p3 | not_reported | not_reported | not_applicable |  | {"units": "not_applicable"} |
| q1 | protocol identity | SYN-B | SYN-B:p1 | reported | M-1 / D-1 / stirred batch / P-60 | not_applicable | Study B used material M-1 to remove dye D-1 in a stirred batch task under protocol P-60. | {} |
| q2 | 60-minute removal | SYN-B | SYN-B:p2 | reported | 82 | percent | At 60 minutes, removal was 82 percent under protocol P-60 | {"budget": "shared screening cap 600 USD","material": "M-1","metric": "removal_at_60_min","pollutant": "D-1","task": "stirred batch removal under protocol P-60","units": "percent"} |
| q3 | confirmation cost and shared cap | SYN-B | SYN-B:p3 | reported | {"confirmation_cost_usd": 300,"shared_cap_usd": 600} | USD | The confirmation run costs 300 USD against the shared 600 USD screening budget | {"units": "USD"} |
| q4 | replicate variance | SYN-B | SYN-B:p3 | not_reported | not_reported | not_applicable |  | {"units": "not_applicable"} |
| q1 | protocol identity | SYN-C | SYN-C:p1 | reported | M-1 / D-2 / stirred batch / P-60 | not_applicable | Study C used material M-1 to remove dye D-2 in a stirred batch task under protocol P-60. | {} |
| q2 | 60-minute removal | SYN-C | SYN-C:p2 | reported | 90 | percent | At 60 minutes, removal was 90 percent under protocol P-60 | {"budget": "shared screening cap 600 USD","material": "M-1","metric": "removal_at_60_min","pollutant": "D-2","task": "stirred batch removal under protocol P-60","units": "percent"} |
| q3 | confirmation cost and shared cap | SYN-C | SYN-C:p3 | reported | {"confirmation_cost_usd": 200,"shared_cap_usd": 600} | USD | The confirmation run costs 200 USD against the shared 600 USD screening budget | {"units": "USD"} |
| q4 | replicate variance | SYN-C | SYN-C:p3 | not_reported | not_reported | not_applicable |  | {"units": "not_applicable"} |

## Retained exclusions / noncomparability

- {"cell_ids": ["c-performance"],"reason": "SYN-C reports dye D-2 rather than D-1; its reported 90 percent remains separate and is not an input to the D-1 mean.","state": "noncomparable"}

Coverage requirement: 3 of 3 in-scope documents represented.
