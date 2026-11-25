# Data schemas

These are executable conventions implemented by `scripts/compare_lib.py`; JSON is UTF-8 and uses no external schema package.

## case.json

Required: string `case_id`. Optional metadata is retained only as needed; `result.json` must use this exact value, not the workorder ID.

## comparison-workorder.json

Top-level required members:

- `case_id`: must match `case.json`;
- `documents`: list of `{source_document_id, path, title}`. Path is relative to the input directory. PDF or text is accepted;
- `agent_specified_proposition_keys`: exact strings allowed for clustering;
- `common_matrix`: `{fields: [field_id, ...], rows: [...]}`;
- `propositions`: list described below;
- `evidence_records`: list described below;
- `conflict_relations`: explicit proposition pairs and declared verdicts;
- `mechanism_attributions`: hypotheses/tests described below;
- `integrated_response`: concise evidence-bounded response;
- `output_contract`: list or dictionary (also permitted in `case.json`; workorder takes precedence).

### Common matrix

```json
{
  "fields": ["task", "material", "pollutant", "metric", "units", "budget"],
  "rows": [
    {
      "field_id": "task",
      "cells": [
        {"source_document_id": "paper-a", "paragraph_id": "a-p1", "value": "adsorption"}
      ]
    }
  ]
}
```

Every row contains every document exactly once. Values may be strings, numbers, lists, dictionaries, `unreported`, or `noncomparable`; null is treated as unreported.

### Proposition

Required members:

- `proposition_id`, `proposition_key`, `topic`, `comparison`, `task`;
- `metric`: `{name, unit}`; unit remains explicit even for dimensionless measures;
- `materials`, `pollutants`: nonempty arrays of exact name strings;
- `claim_scope`: `scoped` or `universal`;
- `scope`: object of applicability conditions, with explicit `unreported` where unknown. Optional `relation_role: scope_extension` identifies an intentionally different coverage domain;
- `evidence_ids`: references into `evidence_records`;
- `strength`: `{wording, statistical_significance}` with significance one of `not_reported`, `reported_significant`, `reported_not_significant`, `not_applicable`;
- `within_paper_limitations`: nonempty string array;
- optional `direction`: `increase`, `decrease`, `no_difference`, `non_monotonic`, or `mixed` only when warranted by a cited observation.

### Evidence record

- `evidence_id`, `source_document_id`, `paragraph_id`;
- `evidence_kind`: `observed_result`, `author_interpretation`, or `speculation`;
- `finding`: source-faithful statement;
- optional `measurements`: list of `{arm, value, unit}`; no imputation;
- optional `direction` and `direction_basis` for observations;
- optional `design`, including `direct_head_to_head` for tested moderators.

Interpretations/speculation cannot carry quantitative direction and cannot substitute for observed results.

### Conflict relation

```json
{
  "relation_id": "R1",
  "proposition_ids": ["P1", "P2"],
  "verdict": "genuine_conflict",
  "rationale": "Same estimand and matched conditions; opposite observed directions; unresolved."
}
```

Only two distinct known propositions are allowed. The validator recomputes a relation from dimensions, scope, and observed directions; it rejects an overclaimed declared verdict.

### Mechanism attribution

- `mechanism_id`, `claim`, `status`;
- `supporting_explanations`: nonempty list of `{explanation, evidence_refs, tested_by?}`;
- `alternative_explanations`: nonempty list of `{explanation, evidence_refs, status}`;
- `direct_comparisons`: list, possibly empty, of `{comparison_id, source_document_id, paragraph_id, evidence_kind, design, moderator, holds_constant}`.

For `supported_by_direct_comparison`, each supporting explanation must name an existing direct comparison through `tested_by`, and at least one direct comparison must be a cited `observed_result` with `direct_head_to_head` design. Speculation anywhere in its support chain is rejected. Alternatives are required even for supported mechanisms.

### Quantitative compatibility gate

The function `quantitative_compatibility` checks task, metric name, metric unit, materials, pollutants, budget reporting, matched applicability conditions, and dataset identity if provided. The pipeline does not calculate pooled effects. Preserve unreported values and choose `incomparable`/`insufficient` where appropriate.
