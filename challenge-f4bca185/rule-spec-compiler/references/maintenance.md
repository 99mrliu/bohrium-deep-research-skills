# Maintenance and extension

## Modifying the compiler

Keep `scripts/rule_spec_compiler.py` Python-3-standard-library-only and deterministic. Run `python3 scripts/test_rule_spec_compiler.py` and `sh examples/run.sh` after every change. Add fixtures for successful conversion, incompatible definitions, invalid JSON/non-finite numbers, and each newly supported output-contract wrapper. Never replace integration artifacts with hand-written mock output.

The bundle contains no README by design. `SKILL.md` is the operating entry point. Preserve its YAML frontmatter to exactly `name` and `description`.

## Stable IDs and compatibility

Rule IDs hash normalized semantics. Do not derive IDs from Python `hash()`, array position, memory address, current time, or a random UUID. When changing normalization, assess whether a stable-ID version transition is necessary and mention it in the audit format. Merge exact duplicate declarations by ID while retaining all provenance.

Any new rule type needs:

1. explicit DSL documentation and conservative validation;
2. default priority and conflict-family policy;
3. a pure transformation that returns a reviewable error instead of guessing;
4. cell-change provenance and missing-value behavior;
5. success, no-op, malformed-value, and conflicting-rule tests.

Do not add automatic rules based merely on a column header. Do not allow a priority to bypass incompatible-rule holds. Expand unit arithmetic only in coherent dimensions using exact `Decimal` factors; units that require affine transforms or contextual interpretation need separately tested semantics rather than silently fitting the ratio table.

## Output changes

The required filenames and nonzero/partial behavior are compatibility surface. New fields should not remove `case_id`, `status`, `sources`, `uncertainty`, `change_records`/`change_log`, `review_queue`, `artifacts`, or declared `output_contract` keys. Preserve direct CSV tables and empty-missing encoding. If a data format cannot be safely emitted, report it as an unresolved/review item rather than fabricating fields.

Keep user provenance contained in paths, sources, and output metadata, not logs. The run accepts no credentials and performs no network operations, repository operations, uploads, or submissions. Secret material is outside the DSL and must never be introduced into config or artifacts.

## Release checklist

- Execute self-tests and the synthetic runner; expected conflict/failure codes are asserted by the runner.
- Compare all artifact hashes across independent reruns.
- Read `result.json`, `execution_plan.json`, `changes.jsonl`, `review_queue.csv`, `audit.md`, and direct CSV outputs.
- Check unknown required contract fields are null plus unresolved, and optional fields are present as null where applicable.
- Verify every synthetic fixture/output is marked `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`.
- Ensure at most 50 UTF-8 text files, each no larger than 500 KB and total no larger than 2 MB; no symlinks, binaries, bytecode cache, machine-specific paths, repository metadata, or unintended README.
- Reject generated `.tmp` files and transient runtime work before packaging.
