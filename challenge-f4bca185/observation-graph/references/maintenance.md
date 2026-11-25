# Maintenance and regression checks

## Preserve the invariant

The non-negotiable invariant is:

> Only a case-authorized, normalized-raw-equal, declared-identity match can be an exact transport duplicate. Every other candidate remains in cleaned output and in the statistical view.

Do not add fuzzy chemical matching, embedding similarity, numeric tolerance, unit conversion, missing-value wildcards, or majority-vote context resolution. Add case-declared fields to blocking/fingerprints instead of guessing equivalence.

Any new merge class requires a new explicit case authorization and certificate rule; adding it to an existing `SAME_*` relation is insufficient. Changes that affect certificates require updating `references/certificates.md`, the audit contract, and synthetic regression evidence together.

## Local checks

Run the generated example from the bundle root:

```sh
sh examples/run.sh
python3 -m py_compile scripts/observation_graph.py
```

The example is `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`, not an official case. Check:

1. `result.json` reports 11 input/cleaned rows and 10 statistical rows.
2. Exactly one candidate is `exact_transport_duplicate` with an allow certificate and no mismatches.
3. Repeated experiment and repeated extraction candidates have deny certificates and remain separately clustered.
4. The condition-mismatch candidate is `same_core_different_context` and names `temperature`.
5. The `dg-conflict` pair is `conflicting_identity`, names `temperature`, remains in different clusters, and both rows remain statistically included.
6. Every input row appears once in `cleaned.csv`; only one row has `_statistical_include=False`.
7. Graph node/edge IDs are unique and all four `SAME_*` relation types use exact evidence, not merge authorization.
8. Every output-contract key occurs in `result.json`; unknown test keys are null and unresolved.

For deterministic verification, hash all eight managed outputs, rerun `examples/run.sh`, hash again, and require exact equality in identical path order. File traversal and all hashes are deterministic and no timestamps are embedded.

## Additional test matrix

Before release, use disposable fixtures inside a designated work area to cover:

- no identity contract plus byte-identical rows: no merge, unresolved uncertainty;
- shared explicit duplicate ID plus different sample/material/source/value/condition: deny with field names;
- same values but missing versus present condition: deny context mismatch;
- nested document/extraction/observation JSON and top-level `data` wrappers;
- CSV, TSV, JSON, and JSONL with equivalent values;
- exact and token-aware declared synonyms, plus a chemical-looking non-alias that must not canonicalize;
- missing `case_id`, empty materials, malformed JSONL, and non-finite JSON: exit 2 plus empty honest artifacts;
- unknown `output_contract` entries: null result value, unresolved field list, and partial status;
- rerun after an invalid case into the same output directory: no stale valid rows survive.

## Scaling and known limits

Candidate pairs are the union of exact blocks and are compared pairwise. Very large blocks can grow quadratically. Do not silently sample or cap them because omitted candidates would lose certificates. If scaling work is needed, partition only by case-authorized disjoint keys and document any recall effect.

Source-row-based node IDs are stable for identical input bytes and file names, not for reordered or renamed inputs. There is no persistent work cache. Output determinism is defined for identical input paths and bytes.

Keep each file UTF-8 text, avoid symlinks/binaries and host-specific paths, and regenerate synthetic outputs with the actual script rather than hand-editing expected certificates.
