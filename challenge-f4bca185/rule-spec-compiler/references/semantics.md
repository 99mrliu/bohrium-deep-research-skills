# Precedence, immutability, and failure semantics

## Compile before execute

Compilation has no data-dependent branch. The compiler reads and hashes declarations, normalizes aliases and rule forms, sorts by `(priority,rule_id)`, folds duplicate identical declarations, validates resources, and detects incompatibilities. It then writes a canonical plan containing the source hashes and compile-time review IDs. Execution uses this frozen register and verifies its bytes at completion. A work copy and output copy must remain equal.

Priorities establish an order for **compatible** stages (mapping → missing → whitespace → declared maps → scalar conversion → identity validation). A lower numeric priority runs first. Explicit priority does not select a winner among incompatible definitions.

## Incompatibility means hold, not overwrite

Different cell parsers/mappings targeting the same field are incompatible even if their priorities differ; so are multiple source-to-target mappings and multiple identity declarations under the conditions identified by the compiler. Every involved rule is marked `enabled:false`, `hold_reason` is included, and a stable `RULE_CONFLICT` review item lists all IDs. The original cell survives unless a separate compatible rule changed it.

Consequences:

- Data rows loaded: final status `partial`, process exit 0.
- No usable data rows: final status `input_error`, process exit 2.
- The full artifact set still shows what did and did not execute.
- A user override may explicitly disable a rule declaration to remove the conflict; no automatic winner exists.

## Row-level safety

Before a conversion, the previous value is retained. Conversion errors produce `CONVERSION_ERROR`; no output substitution occurs. A rename that would destroy a distinct nonempty value produces `FIELD_COLLISION` and leaves the source/target intact. Identity duplicates are retained with `IDENTITY_DUPLICATE`. Missing values are skipped by transformations and serialized as empty CSV cells or empty strings in flat JSON records; no imputation occurs.

JSON non-finite constants and non-finite CSV textual numeric tokens are rejected or quarantined rather than propagated. Result serialization also guards against non-finite output. Nested source values are serialized with deterministic JSON rather than Python representations.

## Run lifecycle and truthful status

1. Create work/output directories and save a `partial` `result.json` before compilation.
2. Refresh that partial result as soon as case identity and contract requirements are known.
3. Freeze the plan before reading data for transformation.
4. Execute declared enabled rules deterministically in input-file/source-row order.
5. Write all outputs, calculate status, and check plan immutability.

`success` (0) requires usable rows, no actionable open review items, valid case/config, and no unresolved required contract field. `partial` (0) retains useful records but signals required human action without pretending the process crashed. `input_error` (2) means no usable rows or an unrecoverable failure. Unknown contract fields are null and explicitly unresolved. Exceptions take a final defensive path that still attempts every required output.

`review_queue.csv` includes compile and runtime findings. `uncertainty` mirrors actionable uncertainty into `result.json`. `changes.jsonl` records only real edits (plus successful renames); it is not an intended-edit log.

## Determinism contract

Canonical JSON uses sorted keys, compact separators, UTF-8, and finite values. CSV uses LF newlines and stable column order. JSONL change sequence follows rule/row execution order. Review IDs are content hashes with duplicates collapsed. Sources carry SHA-256 and byte counts. Paths are case-relative where available. There is no network, random, timestamp, locale-dependent decimal formatting, or process-dependent set order.

Rerunning the same input, options, and configuration must produce byte-identical output artifacts. Changing rule priority/content intentionally changes the relevant plan identity; changing only duplicate source pointers preserves rule IDs but changes provenance and plan hash.

## Boundaries

The compiler is intentionally conservative rather than scientifically omniscient. Unknown units, arithmetic outside the built-in conversion table, ambiguous numeric forms, custom rule semantics outside the DSL, free-text fact extraction, ontology alignment, imputation, and row merging require human-authored declarations or separate reviewed tooling. No claim of source-data correctness follows merely from successful syntax normalization.
