# Observation identity graph audit

- Case ID: `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`
- Schema: `observation-identity-graph/1.0`
- Input observations: **11**
- Cleaned rows retained: **11**
- Statistical-view rows: **10**
- Statistical exclusions (certified transport only): **1**

## Case identity contract

```json
{"allow_exact_transport_duplicates":true,"candidate_identity_fields":["observation_id","duplicate_group"],"declared":true,"identity_fields":["observation_id"],"row_id_field":"observation_id","transport_fields":["observation_id","document_id","extraction_id","experiment_id","sample_id","material","metric","value","unit","temperature","pressure","solvent","atmosphere"]}
```

Automatic merge requires normalized raw equality, equality of every declared transport field, and explicit case authorization. Same values never override source, sample, material, metric, experiment, or full-condition mismatches.

## Decision categories

- `conflicting_identity`: 2
- `exact_transport_duplicate`: 1
- `repeated_experiment`: 3
- `repeated_extraction`: 2
- `same_core_different_context`: 3
- `unresolved`: 2

## Certificates

Every one of 13 candidate decisions has an explicit allow or deny certificate. Deny certificates enumerate `mismatching_fields`; an empty list means evidence was insufficient rather than that contexts were proven equal. Graph `SAME_*` edges are contextual assertions, not merge authorization.

## Statistical view

All rows are retained in `cleaned.csv` and `cleaned.json`. Only certified transport duplicates have `_statistical_include=false`. `cleaned.json` embeds the derived statistical view.

## Uncertainty and limits

- `CONFLICTING_IDENTITY`: Explicit identity candidates with conflicting fields remain unmerged and queued for review.
- `UNRESOLVED_CANDIDATES`: Candidates with insufficient identity evidence remain unmerged and queued for review.
- Normalization is limited to whitespace, numeric spelling, and case-declared exact/token-aware synonyms. No units or chemical identities are inferred.
- Source locators and all original columns are retained.
