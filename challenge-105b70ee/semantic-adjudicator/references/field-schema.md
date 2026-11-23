# Field record schema (result.json → result.field_results[])

One record per requested `field_id`, in the order of `target-fields.json`.

| key | type | rule |
|-|-|-|
| `field_id` | string | copied verbatim from target-fields.json |
| `status` | enum | `reported` \| `not_reported` \| `source_conflict` \| `extraction_failed` |
| `scalar` | string \| null | value exactly as printed, incl. range/inequality form (`92–95`, `> 90`); null unless reported/source_conflict |
| `units` | string \| null | exactly as printed (`mAh g⁻¹`, `%`); null when absent in paper |
| `statistic` | string \| null | printed error/significance (`± 0.4`, `p < 0.05`, `n = 5`) |
| `condition` | string \| null | sample + setting + time point the value holds under; mandatory for numeric reported values |
| `comparator` | string \| null | comparison object for comparative claims; mandatory when the quote is comparative |
| `quote` | string \| null | verbatim sentence (or table line) containing the value; must contain `scalar` as a substring |
| `page` | int \| null | PDF page of the quote (1-based, as printed by the extractor) |
| `paragraph_id` | string \| null | paragraph/sentence id when the workflow has one (`p002.003`), else null |
| `notes` | string | adjudication trace: why accepted/rejected, searched terms, conflicting readings, manual-check hints |

## Claims (result.json → claims[])

| key | rule |
|-|-|
| `kind` | `conclusion` \| `limitation` \| `speculation` |
| `text` | the claim in your words; hedged claims keep hedge words |
| `evidence` | `{quote, page, paragraph_id}` — verbatim, located |
| `source_id` | `MAIN`, `SI1`, … |
| `location` | human-readable `page N/pXXX.YYY` |

## Top-level (output_contract)

`case_id` echoed verbatim from case.json; `status` ∈
`answered` (all fields reported) \| `partial` (mixed or incomplete) \|
`insufficient_evidence` (nothing extractable) \| `input_error` (input
unusable, reason in uncertainties); `result.field_results` as above;
`claims` as above; `uncertainties` mirrors every non-reported field plus
any conflict/fragility notes.
