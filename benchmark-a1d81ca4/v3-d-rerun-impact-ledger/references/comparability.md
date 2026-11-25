# Comparability, reruns, and selective recomputation

## What a semantic rerun proves

`compare_runs.py` consumes two distinct, real, STABLE, full four-item run directories. It validates item IDs, raw-output linkage, rubric components, and score arithmetic before comparing them. A selective two- or three-item run cannot masquerade as a full semantic rerun.

The comparator removes only these declared volatile keys recursively: `run_id`, `raw_output_id`, `score_id`, `run_config_sha256`, `raw_output_file_sha256`, and `generated_at`. It does not remove answers, calculations, raw text, evidence, source hashes, rubric hashes, task hashes, computation hashes, component scores, totals, max scores, selection semantics, bank hashes, or error content. Different error sets make the comparison unequal and return nonzero.

The resulting semantic hash covers canonical raw records, score records, selection, and item-bank hash. Equal semantic hashes are repeatable-execution evidence under this declared policy. **Hash identity is not scientific correctness.** Two runs can repeat the same wrong interpretation, wrong reference answer, or wrong rubric. Conversely, a meaningful dependency change should produce inequality rather than be normalized away.

## Impact classification

`impact.py` compares two four-item bank versions, the materials versions, and the actual old score ledger. For each item it distinguishes changes to:

- `task`;
- `reference_answer`;
- `rubric`;
- `evidence` (including locators and exact quotes);
- `computation` (the executable calculation specification); and
- `source_bytes` (the actual bytes of every evidence material).

Every changed/removed old score ID is listed as affected. Added or changed items are placed in `recompute_item_ids`. A changed global `scoring_semantics` makes all items affected, even if their local JSON is unchanged.

For an unchanged item under unchanged applicable semantics, the report lists the old score ID/hash and a conditional comparability statement. This is selective-recomputation evidence, not permission to silently copy a score into a different full run. Callers must retain the old run lineage and the impact record. The provided example initializes a version-2 run and executes only `recompute_item_ids`; its `selection.json` lists the three recomputed IDs and the one deliberately untouched ID.

## Limitations and agent duties

- Verify calculations and reference answers against the actual paragraph/table content before trusting a score.
- A byte-identical source can still be interpreted incorrectly; a valid evidence quote can be incomplete or misleading.
- Canonical JSON comparison detects semantic JSON changes, not every possible change in external scoring code, interpreter, libraries, environment, or harness. Record those versions/declarations and recompute when they affect applicable semantics.
- Source-byte impact is dependency-based: changing one material affects items citing that material. It does not automatically establish that unrelated materials or unchanged items changed.
- The synthetic helper is deterministic and standard-library-only. Each item uses two binary components for a consistent 0/1/2 score and a maximum of 2; the four-item positive example totals 8/8. Its full marks demonstrate arithmetic/lineage mechanics, not real-world evidence or benchmark validity.
- Successful process gates do not replace expert or agent review. Final results preserve uncertainty, limitations, sources, and change records for that review.
