# Integration report

**SYNTHETIC MINIMAL EXAMPLE — NOT AN OFFICIAL CASE ANSWER**

Case: `SYNTHETIC-95061011-THREE-DOC-001`  
Status: **success**

## Requested responses

### comparability_verdict

```json
{
  "comparable_members": [
    "SYN-A",
    "SYN-B"
  ],
  "basis": "Both report M-1 / D-1, stirred batch protocol P-60, 60-minute removal in percent, and the same 600 USD screening-budget condition.",
  "separate": [
    {
      "source_document_id": "SYN-C",
      "state": "noncomparable",
      "reason": "Its target is D-2, not D-1; the 90 percent value is retained separately."
    }
  ]
}
```

### pooled_result_or_separate_values

```json
{
  "method": "unweighted arithmetic mean requested by q2",
  "member_cell_ids": [
    "a-performance",
    "b-performance"
  ],
  "result": 76,
  "units": "percent removal at 60 minutes",
  "excluded": [
    {
      "source_document_id": "SYN-C",
      "value": 90,
      "units": "percent",
      "state": "noncomparable",
      "reason": "Different pollutant/dye: D-2 rather than D-1."
    }
  ]
}
```

### recommended_next_step

```json
{
  "action": "Run the two M-1 / D-1 confirmation experiments from SYN-A and SYN-B, recording replicate variance.",
  "source_document_ids": [
    "SYN-A",
    "SYN-B"
  ],
  "individual_costs_usd": {
    "SYN-A": 240,
    "SYN-B": 300
  }
}
```

### budget_assessment

```json
{
  "shared_cap_usd": 600,
  "combined_confirmation_cost_usd": 540,
  "remaining_usd": 60,
  "within_budget": true,
  "basis": "240 + 300 = 540 USD for the two requested M-1 / D-1 runs; SYN-C is not substituted because it concerns D-2."
}
```

### open_questions

```json
[
  "Replicate variance is not_reported in SYN-A, SYN-B, and SYN-C; no variance or significance interval can be calculated from these point values.",
  "The 76 percent value is an unweighted mean of two single-run screening values, so its precision and reproducibility remain unknown."
]
```

## Evidence synthesis

### q2-a-b-descriptive-mean

For SYN-A and SYN-B only, the question-requested unweighted arithmetic mean is (70 + 82) / 2 = 76 percent removal at 60 minutes. This is a two-point descriptive mean, not a variance estimate.

- Kind: `quantitative`
- Member cells: `a-performance, b-performance`
- Method: `arithmetic_mean`
- Result: `76 percent`
- Comparability confirmed: task, metric, units, material, pollutant, budget

## Noncomparable and excluded evidence

- {"cell_ids": ["c-performance"],"reason": "SYN-C reports dye D-2 rather than D-1; its reported 90 percent remains separate and is not an input to the D-1 mean.","state": "noncomparable"}

## Uncertainty

- All three sources state that replicate variance was not reported.
- The requested arithmetic mean describes only two screening observations and is not a statistical pooled uncertainty estimate.

## Sources

- `SYN-A` (`corpus/syn-a.txt`), paragraphs: `SYN-A:p1`, `SYN-A:p2`, `SYN-A:p3`
- `SYN-B` (`corpus/syn-b.txt`), paragraphs: `SYN-B:p1`, `SYN-B:p2`, `SYN-B:p3`
- `SYN-C` (`corpus/syn-c.txt`), paragraphs: `SYN-C:p1`, `SYN-C:p2`, `SYN-C:p3`

## Change records

- {"change": "Mapped q1-q4 directly to the five original output-contract keys.","reason": "The response follows this workorder's requested decisions rather than a fixed extraction schema."}
- {"change": "Excluded SYN-C from the 76 percent arithmetic mean and retained its separate 90 percent result.","reason": "Pollutant/dye differs: D-2 versus D-1."}
- {"change": "Retained replicate variance as not_reported and completed the run with success status.","reason": "All requested work was answered; absence and noncomparability are scientific findings, not incomplete processing."}
