# Maintenance and validation

Maintain this Skill as an adjudicator, not a general cleaning framework. Changes must preserve deterministic ordering, source independence, exact anchors, honest partial results, and the prohibition on scientific inference.

## Before editing

Run the marked synthetic workflow and inspect, not merely parse, the conflict, normalized note, unsupported label, and blank unit/value:

```bash
bash examples/run.sh
python3 scripts/self_check.py
```

`self_check.py` performs two runs and compares SHA-256 for all seven outputs, validates CSV/JSON/JSONL, checks all four states and exact anchors, verifies nested contract completion and the null unknown field, and tests missing-evidence plus malformed-case behavior. Its temporary fixtures are disposable and not official data.

## Safe extensions

Prefer new tests over broader heuristics. Reasonable extensions include more explicit case-declared file-role aliases, stronger record identity predicates, and additional typed locators. Each must leave existing anchor evidence inspectable. Add an unresolved warning when role/entity ambiguity cannot be resolved.

Do not add answer tables, literature-specific numerical priors, hidden unit conversion, fuzzy string replacement, network lookup, timestamps, random sampling, non-standard Python packages, or automatic conflict resolution. Do not turn every supplied table into an extractor merely to increase recall. PDF support stays optional and locator-preserving; OCR without reliable page/text anchors must remain unresolved.

## Contract changes

Test all supported shapes independently: a field dictionary, list of strings, list of field dictionaries, and nested `fields`/`properties` with `required`. Only known semantics should be populated. A new unknown name must remain `null` and be listed in `unresolved_fields`; do not fill a plausible count, grade, score, label, answer, or status from an unrelated artifact. Preserve common `case_id` wrappers.

## Failure behavior

Missing case/task must return nonzero while leaving readable artifacts and a contract-complete result whenever a case contract could be parsed. Missing evidence is a valid partial adjudication, not malformed input. Early artifact writing itself must be exercised after changes to result construction. A runtime exception may return 1, but should retain partial outputs and identify an error rather than emitting success.

## Bundle checks

Keep `SKILL.md` frontmatter limited to `name` and `description`; do not add a README. Keep every example file and every generated example artifact visibly marked `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`. Keep paths portable, scripts standard-library-only, and the bundle within 50 UTF-8 text files/2 MB total, each file below 500 KB, with no symlinks/binaries. Do not commit generated work directories, bytecode, caches, credentials, or temporary failure fixtures.
