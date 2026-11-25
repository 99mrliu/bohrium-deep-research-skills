# Observation graph semantics

## Identity is layered

A document describes a report. An extraction is a process/view producing observations. An observation binds a sample/material/metric/value to a complete experimental context. These identities are deliberately not collapsed.

- Document identity comes from declared document/source identifiers; filename is a fallback node identity only.
- Extraction identity comes from a declared extraction identifier; an unidentified extraction is attached to its document but is not treated as proof of repeated extraction.
- Observation node IDs are deterministic hashes of source file, source row, and normalized raw record. The declared observation ID remains a separate property.
- Experiment and sample IDs never become wildcards when absent.

The graph contains nodes and evidence edges, not just rows in a cluster. `SAME_EXTRACTION`, `SAME_SAMPLE`, `SAME_CONDITION`, and `SAME_EXPERIMENT` state one exact relation each. They are not transitive merge permissions. In particular, same sample plus same values does not imply same observation.

## Full condition fingerprint

The fingerprint is a SHA-256 digest (displayed as a deterministic prefix) of canonical JSON for the complete condition map. Keys are sorted and values receive only whitespace/case-fold comparison and decimal-spelling normalization. Nested `conditions` keys are represented as `conditions.<key>`. Declared condition fields and all condition-prefixed fields are included.

A missing key and a present key differ. A missing value is not a matching wildcard. No unit conversion is applied: `298 K` and `0.298 kK` are not guessed to be equal. Solvent, catalyst, atmosphere, pressure, temperature, and undeclared condition-prefixed fields remain decision context.

## Blocking versus adjudication

Blocking is recall-oriented and constructs a union of candidates from:

1. each case-declared candidate identity key independently;
2. document + sample + material + metric;
3. sample + material + metric + complete condition fingerprint;
4. sample + material + metric;
5. experiment + material + metric.

A shared duplicate-group key creates a candidate even when observation IDs differ. This is required to expose conflicting explicit identities. All candidates are adjudicated; no candidate disappears merely because values match.

Blocking does not create evidence. A pair from a broad block can end unresolved. Pair ordering, node IDs, decision IDs, cluster IDs, and output ordering are deterministic.

## Decision precedence

The adjudicator applies conservative precedence:

1. **Exact transport duplicate:** normalized raw mappings are equal, all declared transport fields match, at least one declared identity matches, and the case explicitly enables auto-deduplication. Only this class receives `action=merge`.
2. **Conflicting identity:** an explicit observation/duplicate identity matches but any raw/context field differs. The conflict is retained for review.
3. **Unauthorized exact values:** raw values match without contract authorization; unresolved, never merged.
4. **Repeated extraction:** experiment and semantic observation fields and full conditions agree, but row/extraction identity differs. Retained as evidence repetition.
5. **Repeated experiment:** different nonempty experiment IDs share sample/material/metric/full conditions. This remains distinct even when documents, values, or units differ; differing fields are listed.
6. **Same core, different context:** document/sample/material/metric core agrees but full condition fingerprints differ. Retained.
7. **Unresolved:** all remaining candidates lacking enough proof. Equal values cannot resolve missing experiment or source context.

A transport component is formed only by allow-certified edges. If future rules permit components larger than two, every pair still needs its own certificate; connectivity never creates an implicit pairwise certificate.

## Retention and statistics

`cleaned.csv` and `cleaned.json.rows` contain every input row. `_disposition` and `_cluster_id` expose adjudication without deleting evidence. A transport duplicate is still present with `_statistical_include=false`.

Only rows with an incoming allow-certified transport relationship are excluded from `cleaned.json.statistical_view`. Cluster representatives are selected deterministically by source filename and source row. Repeated extractions, repeated experiments, different contexts, conflicts, and unresolved candidates all remain included.

## Limits

The implementation does not infer chemical equivalence, convert units, resolve samples across aliases unless the case declares exact/token-aware synonyms, or auto-resolve review items. Candidate generation is exact-key based; a typo in every block key may produce no candidate and therefore no pair decision. This conservative omission is preferable to a guessed merge and must be considered during case-specific maintenance.
