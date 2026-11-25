# Input and adjudication formats

All examples in this document are **SYNTHETIC interface fragments**, not scientific claims or official answers.

## Inputs

The runtime reads:

- `/input/case.json`: object with `case_id`; optional `synthetic: true` labels an authored example;
- `/input/target-fields.json`: a non-empty list, `{ "fields": [...] }`, `{ "target_fields": [...] }`, a single field object, or a mapping keyed by field ID;
- `/input/task.md`: UTF-8 original task text, hashed into the contract.

Each field requires a unique string `field_id` (`id` is accepted as an input alias). The compiler retains the unmodified source specification inside `source_spec` for audit.

### Contract aliases

| Canonical axis | Accepted explicit schema keys |
|---|---|
| `metric_identity` | `metric_identity`, `metric`, `metric_name`, `indicator`, `measure` |
| `subject_entity` | `subject_entity`, `subject`, `entity`, `material`, `system` |
| `expected_value_form` | `expected_value_form`, `value_form`, `answer_type`, `expected_type`, `type` |
| `requested_unit` | `requested_unit`, `unit`, `units`, `requested_units` |
| `statistic` | `statistic`, `stat`, `aggregation`, `summary_statistic` |
| `required_condition` | `required_condition`, `experimental_condition`, `condition`, `conditions` |
| `comparator` | `comparator`, `comparison`, `baseline` |
| `source_scope` | `source_scope`, `scope`, `allowed_sources` |
| `modality` | `modality`, `conclusion_modality` |

`kind` or `field_kind` equal to `conclusion` enables conclusion-modality validation. Other kinds default `modality` to `not_applicable` when no explicit modality is supplied. Missing semantic axes become `UNSPECIFIED_REQUIRES_CONTRACT_AMENDMENT` and a blocking issue; question text alone is not silently promoted to a structured interpretation.

A source scope may be a list of source IDs, `{ "source_ids": [...] }`, `all_sources`, or `all_sources_in_source_register`. Other structured scopes must be enforced through the agent's `source_scope` test rationale; the compiler cannot evaluate arbitrary scope expressions.

## Contract amendments

Before source candidate review, resolve only needed axes:

```json
{
  "amendments": [
    {
      "field_id": "F_SYNTHETIC",
      "set": {
        "statistic": "standard deviation",
        "required_condition": "dose=5 mg AND time=24 h"
      },
      "rationale": "The SYNTHETIC question explicitly asks for SD at 5 mg and 24 h."
    }
  ]
}
```

An amendment cannot modify test IDs, source specifications, case ID, or decision outcomes. It regenerates the acceptance tests and contract hash. Old adjudication files therefore fail closed rather than silently carrying pass decisions to a changed contract.

## Source register

```json
{
  "sources": [{"source_id": "S1", "title": "SYNTHETIC excerpt"}],
  "paragraphs": [
    {
      "source_id": "S1",
      "paragraph_id": "p1",
      "page": 2,
      "text": "SYNTHETIC exact paragraph text."
    }
  ]
}
```

`text`, `source_id`, and `paragraph_id` must be non-empty strings. `page` may be a string, number, or null. Quotes are checked by exact, case-sensitive substring inclusion with no whitespace or Unicode normalization. The evidence page must equal the registered page exactly.

## Adjudication envelope

```json
{
  "case_id": "SYNTHETIC-CASE",
  "contract_sha256": "copy the exact current contract hash",
  "decisions": []
}
```

The decision list must cover every contract field exactly once. All field records can include `notes`; `reported` and `source_conflict` require `acceptance_checks`. Every precompiled test ID must occur once, with `passed: true` and a non-empty semantic rationale. Any `passed: false` rejects the entire proposed `reported`/`source_conflict` decision. This is intentional: use a rejected-candidate record, conflict, failure, or a correct alternative rather than accepting a failed candidate.

### Reported decision

```json
{
  "field_id": "F_SYNTHETIC",
  "status": "reported",
  "scalar": 72,
  "verbatim_value": "72",
  "units": "%",
  "statistic": "single reported value",
  "experimental_condition": "temperature=120 °C AND solvent=toluene",
  "comparator": null,
  "modality": "not_applicable",
  "evidence": [
    {
      "source_id": "S1",
      "page": 2,
      "paragraph_id": "p1",
      "quote": "At 120 °C in toluene, Catalyst X gave a yield of 72%."
    }
  ],
  "acceptance_checks": [
    {
      "test_id": "F_SYNTHETIC::metric_identity",
      "passed": true,
      "rationale": "SYNTHETIC rationale..."
    }
  ],
  "notes": "Include all ten test rows in a real decision.",
  "rejected_candidates": [
    {
      "verbatim_value": "72",
      "failed_test_id": "F_SYNTHETIC::required_condition",
      "reason": "Same number but 80 °C, not 120 °C.",
      "evidence": {
        "source_id": "S1",
        "page": 1,
        "paragraph_id": "p0",
        "quote": "At 80 °C in toluene, Catalyst X gave a yield of 72%."
      }
    }
  ]
}
```

A reported decision has exactly one primary evidence object. The output copies its paragraph ID and quote to the required top-level field keys and mirrors `experimental_condition` into `condition`. `verbatim_value` must occur in the quote. A string scalar exactly equals `verbatim_value`; numeric values preserve source spelling through `verbatim_value` and are not unit-converted. Lists/objects are not accepted as `scalar`; represent a range/list according to the task with a scalar string when that exact form is requested.

Conclusion decisions use the same shape but normally have null units/statistic/comparator and a string scalar containing the full verbatim statement. Set `modality` to one of `author_conclusion`, `author_speculation`, `author_limitation`, `reported_fact`, `mixed`, or `unclear`. A specific contract modality must match; `classify_from_wording` permits any listed classification supported by the text.

### Not-reported decision

```json
{
  "field_id": "F_SYNTHETIC_SD",
  "status": "not_reported",
  "notes": "No SD located; replicate count is not substituted.",
  "search_record": {
    "paragraphs_searched": [
      {"source_id": "S1", "paragraph_id": "p1"},
      {"source_id": "S1", "paragraph_id": "p2"}
    ],
    "rationale": "These are all in-scope passages that could contain the requested value; neither reports SD."
  }
}
```

Searched references must exist in the register and respect source-ID scope metadata. Null values are retained; no zero or negative-looking placeholder is inserted.

### Source-conflict decision

```json
{
  "field_id": "F_SYNTHETIC_CONFLICT",
  "status": "source_conflict",
  "modality": "not_applicable",
  "notes": "Both values meet semantics and remain unresolved.",
  "acceptance_checks": [],
  "conflict_candidates": [
    {
      "scalar": 90,
      "verbatim_value": "90",
      "units": "%",
      "statistic": "single reported value",
      "experimental_condition": "condition A",
      "comparator": null,
      "evidence": {"source_id": "S1", "page": 2, "paragraph_id": "p1", "quote": "Exact 90% quote."}
    },
    {
      "scalar": 88,
      "verbatim_value": "88",
      "units": "%",
      "statistic": "single reported value",
      "experimental_condition": "condition A",
      "comparator": null,
      "evidence": {"source_id": "S1", "page": 3, "paragraph_id": "p2", "quote": "Exact 88% quote."}
    }
  ]
}
```

The empty `acceptance_checks` above is only a shape illustration; a real conflict decision needs the complete precompiled set exactly as a reported decision does. At least two distinct evidence locations or quotes are required. Field scalar is null and each candidate retains its own units and conditions.

### Extraction-failed decision

```json
{
  "field_id": "F_SYNTHETIC_UNREADABLE",
  "status": "extraction_failed",
  "failure_reason": "The only target cell is unreadable in the supplied material; manual retrieval is required.",
  "notes": "This is not a claim of absence.",
  "evidence": [
    {"source_id": "S1", "page": 3, "paragraph_id": "p3", "quote": "Conversion cell: [illegible]."}
  ]
}
```

Evidence is optional for this status but, when provided, obeys exact source binding.

## Output and overall state

Each output field always contains `field_id`, `status`, `scalar`, `units`, `statistic`, `experimental_condition`, `condition`, `comparator`, `paragraph_id`, `quote`, `evidence`, and `notes`, with nulls for inapplicable scalar/evidence values. Extra audit keys may include `verbatim_value`, `modality`, `acceptance_checks`, `rejected_candidates`, `conflict_candidates`, `search_record`, and `failure_reason`.

Overall `status` is computed conservatively from field states: all reported = `answered`; some reported = `partial`; none reported = `insufficient_evidence`; unusable input = `input_error`. No conflict candidate is promoted into the answer automatically.
