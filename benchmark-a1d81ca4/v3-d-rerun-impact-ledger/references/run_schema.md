# Run schema and status contract

All records are UTF-8 JSON unless their suffix is `.txt` or `.md`. Hashes are lowercase SHA-256 hex digests computed from actual bytes at execution time. JSON semantic hashes use UTF-8, sorted object keys, no insignificant whitespace, and explicit canonicalization; source-file hashes always use the original bytes, not JSON normalization.

## Directory records

Each `init_run.py` call creates a unique `run-*` directory under the explicit work root. It writes:

- `run_config.json`: run ID, actual input paths, item-bank version/hash, real UTC creation time, explicit time/output budgets, Python implementation/version and platform, and declared model/harness. Model/harness come only from CLI or their explicit environment variables; otherwise they are `unknown`.
- `manifest.json`: original case ID, case/task/material/item-bank byte records, config hash, early `PARTIAL`, `success:false`, and tool/budget declarations.
- The early result: every dynamic output-contract field is top-level with the original case ID. It is a safe partial and never a success placeholder.

`run_command.py` adds actual `command.stdout.txt`, `command.stderr.txt`, `command_record.json`, and `execution.json`. The command record includes argv, explicit cwd, `shell:false`, start/finish UTC, monotonic duration, timeout, returncode/exit code, log hashes, expected-output presence/bytes/hashes, output-budget use, and failure reasons. Scorer-created raw outputs and score records remain in that run tree.

Manifests, configs, command records, execution records, and helper raw-output files use create-once writes and are set read-only. A rerun must use a new run directory. Scripts never replace an existing audit record. Early/final `result.json` is an explicitly mutable publication view, not an audit manifest; publication is atomic. Compare/impact reports use create-once names.

## Independent output-contract parsing

`case.output_contract` is parsed independently of the synthetic case. Supported shapes are:

- a top-level list of field-name strings;
- `fields`, `required_fields`, `required_top_fields`, or `required_top_level_fields` lists containing strings and/or descriptor objects with a nonempty `name`;
- a direct object mapping each field name to a JSON type string, a descriptor/metadata object, or null; and
- a `properties` object using the same field-to-descriptor mapping.

List containers and `properties` can be combined, with nonconflicting descriptors merged. Descriptors may declare `type` as `object`, `array`, `string`, `number`, `integer`, `boolean`, or `null`, or a nonempty union list of those types. Final payloads are checked against those declarations and against the exact dynamic top-level field set. `case_id` and `status` are always added top-level when omitted by the contract; the original case ID is never replaced.

Known fields bind to actual validated content. `items`, `benchmark_draft`, and `questions` are the full four bank items, including every original task, reference answer, rubric, evidence, computation, and metadata property plus raw answer, complete raw/score records, component scores, and lineage IDs. `item_bank` is the original bank object with those full published items. `scores` is the complete four-score list; `score_report` and `rollup` contain independently summed totals; `summary`, `sources`, `run_manifest`, `uncertainty`, `change_records`, `limitations`, and `success` have their corresponding process/run content.

An unrecognized or unbound field remains present with its declared typed empty value (`[]`, `{}`, `""`, `false`, `0`, or null; untyped unknown fields use null) and gates the publication to PARTIAL. A known binding that violates its declared type is likewise reset to a typed empty value and gates SUCCESS. These conditions are reported rather than silently dropped or fabricated. Failed/partial finalization exits nonzero by default even though the honest PARTIAL result is written.

## Statuses

- `PARTIAL`: initialization happened, final execution/lineage gates have not all passed, or finalization failed. `success` is false.
- `STABLE`: only in `execution.json`; the supplied command launched, exited zero before timeout, stayed within the checked output budget, and produced every expected regular file. It is a process status only.
- `FAILED`: nonzero return, timeout, launch failure, missing expected output, or output-budget overflow. Any one condition prevents STABLE. The wrapper exits nonzero.
- `SUCCESS`: only the final publication after a STABLE full run, exactly four matching item/raw/score IDs, empty errors, valid source/config/raw/reference-answer/rubric lineage, valid rubric and score arithmetic, all declared fields bound to known content, and a dynamic top-level contract/type check.
- A failed run can produce only a `PARTIAL` result. Default finalization then exits nonzero. `--allow-partial` merely acknowledges deliberate partial publication; it never changes status to SUCCESS or STABLE.

`STABLE` does not mean factually, scientifically, or clinically correct. All scores are records produced by a specified scorer; the agent remains responsible for source-conditioned content correctness.

## Raw output and score lineage

For each of exactly four bank items:

1. The raw record has the item ID plus canonical task, reference-answer, rubric, and computation hashes.
2. Evidence records preserve material name, locator, exact quote, quote hash, and actual source-file byte hash.
3. Raw text and the actual raw JSON file have separate hashes. `raw_output_id` links the item to that raw evidence.
4. The score record carries that raw ID, raw file/text hashes, run-config hash, rubric hash, component scores, score/max, and its own score ID.
5. `run_config.json` binds the bank bytes and input materials. `execution.json` binds the initial manifest, config, and actual command record.
6. Finalization verifies all links and sums component scores. Rubric component points must sum to max score; all four max scores and item scores are rolled up independently.

A missing, duplicated, extra, or mismatched item/raw/score ID fails the gate. A score with correct arithmetic but wrong lineage fails too.

## Budgets, errors, and versions

Budgets have no hidden defaults in `init_run.py`; both are required explicit numeric arguments. The command timeout cannot exceed the run time budget. The output budget applies to the declared expected-output files, so callers must list score/error/selection and any other contract-critical outputs. Unlisted files are still preserved when the scorer creates them, but are not counted by that budget check.

Python/platform versions describe the executing interpreter and OS, not an invented model. Command stderr may be empty on success. `errors.json` is scorer semantic/process error evidence and must be `[]` for comparison or SUCCESS. Compare rejects non-STABLE or partial/selective trees.

Bank `bank_version` identifies the dependency set; `scoring_semantics` identifies applicable aggregation/answer-comparison semantics. Impact checks task, reference answer, rubric, evidence, computation, and actual evidence-source bytes. Added/removed items affect corresponding scores. Changed applicable global semantics makes every item require recomputation. Unaffected scores remain comparable only under unchanged item dependencies and applicable semantics.
