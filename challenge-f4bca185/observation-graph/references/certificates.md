# Merge allow and deny certificates

Every candidate pair in `duplicate_decisions.jsonl` has a stable `decision_id`, left/right node IDs and declared observation IDs, `action`, `category`, `cluster_relationship`, and one certificate.

## Allow certificate

An allow certificate is issued only when all conditions hold:

- the case has a declared identity contract;
- `allow_exact_transport_duplicates` (or `auto_deduplicate`) is explicitly true;
- at least one candidate identity field is nonempty and equal;
- every declared transport field is equal under minimal comparison;
- complete normalized raw dictionaries match, including all condition fields.

Example shape:

```json
{
  "action": "merge",
  "category": "exact_transport_duplicate",
  "certificate": {
    "certificate_type": "allow",
    "rule": "declared_exact_transport_identity",
    "matched_fields": ["observation_id", "normalized_raw"],
    "mismatching_fields": [],
    "left_observation_node_id": "obs_...",
    "right_observation_node_id": "obs_...",
    "explanation": "..."
  }
}
```

An allow certificate with any mismatching field is an internal consistency failure and aborts the case as invalid rather than emitting an unjustified merge.

## Deny certificate

Each rejected candidate has `certificate_type="deny"` and `action="reject"`. `rule` states the exact reason. `matched_fields` records supporting similarities, never authorization. `mismatching_fields` lists detected differences, including missing-left/missing-right annotations. The list includes canonical observation/duplicate/extraction/document/sample/experiment/material/metric/value/unit fields, condition keys, and differing undeclared raw keys.

Examples of expected rules:

- `explicit_identity_context_conflict`: an explicit duplicate ID matches but `temperature`, `value`, sample, or another field differs;
- `same_experiment_observation_distinct_extraction`: repeated extraction is not transport duplication;
- `distinct_experiment_same_condition`: repeated experiment is retained;
- `full_condition_fingerprint_mismatch`: condition keys are named individually;
- `exact_values_without_identity_authorization`: equal values lack contract permission;
- `same_semantics_without_experiment_or_identity_proof` or `insufficient_evidence`: unresolved.

A deny certificate may have no mismatches only when evidence is insufficient. That empty list must not be read as certified equality. The explanation carries this distinction.

## Review mapping

All rejected candidates enter `review_queue.csv`. `conflicting_identity` and `unresolved` are `needs_review` at high priority. Repeated extraction, repeated experiment, and same-core/different-context are `informational_retained` at medium priority because retaining them is intentional even though a curator may inspect the classification.

The queue repeats decision IDs and mismatching fields so a reviewer never needs to infer the reason from a cluster label. No review status is automatically resolved.

## Statistical exclusion change

For every non-representative transport row, `changes.jsonl` contains a `statistical_view_exclusion` record linking the observation and cluster. The `before` value is true and `after` is false. No original field is changed to accomplish deduplication; only statistical inclusion changes.

Declared exact/token-aware synonym edits produce separate `declared_synonym_canonicalization` records with before/after values and a no-chemical-inference reason.
