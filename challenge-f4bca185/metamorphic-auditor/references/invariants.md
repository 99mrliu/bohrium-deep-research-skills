# Process invariant and severity reference

## Formal frame and severity

Let `R` be all raw data rows after a fresh disk reload, and let `K`, `D`, and `X` be kept, duplicate, and rejected dispositions. The required partition is:

`R = K disjoint-union D disjoint-union X`, with exactly one disposition per raw row.

Let `T` be the permitted transformation: NFC string normalization, removal of leading/trailing Unicode whitespace, and only case-declared, recomputable unit derivations into missing target cells. No other cell transformation is implicitly permitted.

- **BLOCKER**: cannot establish lineage, conservation, immutability, JSON safety/completeness, or artifact interpretation. Delivery is blocked.
- **HIGH**: conversion, dedup-context, determinism/metamorphism, or ambiguous-lineage violation. Blocking scientific-process risk; inspect source context.
- **MEDIUM**: a declared derivation needs human confirmation or nonblocking coverage documentation is incomplete.
- **LOW**: advisory only. The implementation currently emits no LOW counterexamples.

`status` and `verification_status` are deliberately separate: `success/pass` means the tested invariants passed and no blocking human review remains; `partial/pass` means invariants passed but blocking source-context review remains; `partial/fail` means candidate processing occurred but verification failed; `input_error/fail` means case/material/candidate input was invalid or unavailable. Exit status follows verification, not human-review completion. Any unresolved contract field is null and named, never silently satisfied.

## Independent checks

### 1. `row_conservation_disposition_partition`

For every raw source ID, the union of kept CSV rows and duplicate/rejected entries in `changes.jsonl` must contain exactly one disposition. A kept row cannot also be excluded. Unknown or repeated dispositions fail with the source ID and observed disposition list. Because the conservative policy defines no valid rejection rule, every `rejected` disposition is itself a BLOCKER; otherwise arbitrary rejection could hide rows from scalar checks. Kept rows are the candidate, not a checksum proxy for processing.

### 2. `raw_value_immutability`

For each kept/raw pair and every original column, require `candidate = T(raw)`. Dropped columns, cell edits, coercion, internal-space collapse, unrequested imputation, and target loss are counterexamples with expected, raw, and observed values. Raw CSV/JSON values are loaded without trimming so the check cannot be weakened by its own loader.

### 3. `no_fabricated_missing`

If `raw` is blank or a recognized missing token (`NA`, `N/A`, `null`, `none`, `NaN`, `-`, `--`, case-insensitive), a substantive candidate value is forbidden unless it exactly matches a declared unit derivation. A converted value remains a derivation, not observational evidence. Unknown missing conventions are not guessed.

### 4. `unit_conversion_recomputation`

Each conversion declares source/target fields, factor `a`, and offset `b`. For available raw source `x`, independently compute decimal `a*x+b`; a nonmissing candidate target must agree within `max(1e-9, 1e-9*abs(expected))`. The normalizer fills only a missing target and records the derivation. Existing inconsistent targets are not silently rewritten.

### 5. `dedup_context_non_interference`

Dedup is disabled unless explicitly configured. If enabled, an excluded duplicate must have a kept `duplicate_of` row with identical full normalized original row, configured keys, and configured context. Thus equal bibliographic keys in different contexts cannot cancel each other. Cross-source scientific equivalence is not inferred.

### 6. `deterministic_rerun`

Two fresh calls to the pure normalizer over independent deep copies must emit the same semantic kept-row multiset and byte-equivalent canonical change objects. This test uses no saved run state. Candidate files are separately reloaded from disk. SHA-256 values in `result.json` are evidence inventories, not substitutes for invariants.

### 7. `column_order_row_order_metamorphic_invariance`

Reverse input rows and columns and rerun. The kept original-field multiset and `(full row, disposition)` group counts must agree with the base run. Source IDs are retained only as lineage and excluded from semantic multiset comparison. Reordering exact duplicates may select another equivalent representative; group counts and kept semantic rows must not change.

### 8. `whitespace_noise_metamorphism`

Add leading spaces/trailing tabs to nonmissing raw cells and inject an irrelevant `_metamorphic_irrelevant_noise` field. After normalizing only declared original columns, the kept original-field multiset must be unchanged. This detects accidental internal processing based on presentation noise. It does not license trimming meaningful whitespace inside a value.

### 9. `json_finite_value_completeness`

Strict JSON parsing rejects duplicate keys, `NaN`, and infinities. Finite trees are required for all artifacts. `cleaned.json` must expose a list through `cleaned`, `records`, `rows`, `data`, or `items`; every row must be an object. Its length, field sets, row order, and every cell must agree with `cleaned.csv`. Empty candidate artifacts produced after an input error never erase the recorded failure.

### 10. `review_coverage`

After writing, the review CSV is reloaded. Every non-review-coverage counterexample ID and every `review_required` change ID must occur. A missing queue row becomes a BLOCKER and triggers deterministic queue reconstruction. Queue ordering is blocking impact first, then BLOCKER/HIGH/MEDIUM/LOW, check, locator, and IDs. With no failures or reviewable transformations, a LOW first-raw-row spot-check prevents an empty human sample; it is not statistical acceptance.

### 11. `source_locator_validity`

Generated lineage uses `relative/material/path::row=N`; `_source_file` and `_source_row` must independently agree. The relative path must identify a material reloaded in this run and the 1-based data row must exist. Unlabelled candidates may use exact normalized matching only as a fallback; ambiguous duplicate matches are HIGH counterexamples and recommend explicit `_source_id`.

## Metamorphic limits

These relations are intentionally partial. Determinism cannot prove semantic correctness; exact-context dedup cannot prove two records describe different works; a conversion identity cannot justify an undeclared unit; JSON validity cannot establish scientific completeness; and source-location validity cannot establish source credibility. Passing all checks means only that the declared process properties held on the supplied materials. Scientific conflict, source selection, and domain validity remain human responsibilities.
