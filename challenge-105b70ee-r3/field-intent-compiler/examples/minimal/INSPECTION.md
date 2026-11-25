# SYNTHETIC minimal example — execution inspection

**All inputs, sources, values, decisions, and generated outputs in this example are SYNTHETIC. This is not a formal case, a scientific claim, or a prepared official answer.**

## Environment and entry point

- Interpreter used for inspection: `python3` (system interpreter; stdlib only).
- Working directory: the skill bundle root; commands below use only portable relative paths.
- Initialization was run before `agent/decisions.json` was finalized. The inspected source register is an agent-authored SYNTHETIC artifact, not automatic PDF extraction.

## 1. Compile skeleton and tests, then adjudicate

Commands actually run:

```sh
python3 scripts/field_contract.py init \
  --input-dir examples/minimal/input \
  --work examples/minimal/work \
  --output examples/minimal/output
```

Observations after `init` and before `finalize`:

- Exit code was 0 with no stdout/stderr.
- `output/result.json` already contained all five field IDs in both mirrored arrays. Every field was conservatively `extraction_failed`, had a null scalar, and said `Awaiting agent-authored adjudication.`
- Overall skeleton status was `insufficient_evidence`; no value or source evidence was present.
- `work/acceptance-contract.json` contained ten pending tests for each field. Contract SHA-256 was `37cb8680bc58438b9f359bf742193382d03b8b45d12ecfa661f1ed2d08ca3acf`.
- `work/runtime-events.json` events one and two both recorded `candidate_values_read: false`.

Command actually run after agent-authored decisions were supplied:

```sh
python3 scripts/field_contract.py finalize \
  --work examples/minimal/work \
  --output examples/minimal/output \
  --source-register examples/minimal/agent/source-register.json \
  --decisions examples/minimal/agent/decisions.json
```

Observations:

- Exit code was 0 with no stdout/stderr.
- `output/result.json` and `output/contract-audit.md` were generated and both labeled `SYNTHETIC`.
- Overall status was `partial` with two `reported` fields and three explicit unresolved fields.
- The decision contract hash matched the precompiled contract hash; runtime event three recorded candidate adjudication only after events one and two.

The combined replay command was also run successfully:

```sh
sh examples/minimal/run.sh
```

Observed stdout:

```text
SYNTHETIC example complete: examples/minimal/output/result.json and contract-audit.md
```

## 2. Output inspection

The generated `output/result.json` was read directly. Key observations:

- `F_YIELD_120C`: `reported`, scalar `72`, verbatim value `"72"`, unit `%`, exact paragraph `p-yield-120C`. Its condition and alias are both `temperature=120 °C AND solvent=toluene`.
- The rejected yield candidate is also literal `72`, but its exact quote is at `80 °C` in `p-decoy-80C`. It is recorded under `rejected_candidates` with failed test `F_YIELD_120C::required_condition`. The accepted `72` comes from the separate `120 °C` paragraph; identical number/quote text alone did not determine acceptance.
- `F_YIELD_SD_120C`: `not_reported`, null scalar, and a search record covering all seven registered paragraphs. The three-replicate mention was not converted into an SD or zero.
- `F_SELECTIVITY_120C`: `source_conflict`, null field scalar, and two retained candidates (`90` and `88`) with distinct exact quotes at `p-selectivity-a` and `p-selectivity-b`. Neither was silently selected.
- `F_CONVERSION_120C`: `extraction_failed`, null scalar, exact `[illegible]` location, and a readability/manual-recovery reason distinct from absence.
- `F_AUTHOR_OUTLOOK`: `reported` with the complete hedged sentence and `modality: author_speculation`; the corresponding claim kind is also `author_speculation`.
- `result.fields` equals `result.field_results`; each contains exactly one record per input field ID. All required scalar/unit/statistic/condition/comparator/location/evidence keys are present, with nulls where unresolved or inapplicable.
- `uncertainties` contains the not-reported, conflict, and failed fields. `sources` and three ordered `change_records` are present.

The generated `output/contract-audit.md` was also read. It contains the complete pre-candidate axis contract for every field, all test definitions, semantic pass rationales, the explicit decoy rejection, both conflict candidates, exact evidence quotes/pages, failure/search details, and unresolved items.

## 3. Positive and negative regression tests

Command actually run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_field_contract.py
```

Observed summary:

```text
Ran 5 tests in 0.046s

OK
```

The five tests covered:

1. **ordering**: a complete conservative skeleton and all pending tests exist while both initial runtime events say candidates have not been read;
2. **synthetic end-to-end output**: all statuses, exact correct paragraph, mirrored arrays, null conflict scalar, speculative modality, and explicit decoy rejection;
3. **negative same-number/wrong-condition control**: changing the proposed yield evidence to the decoy `80 °C` paragraph and marking its required-condition check false makes finalization return 2; the test also verifies that the conservative skeleton is not overwritten;
4. **negative exact-binding control**: attaching a literal quote from the decoy paragraph to the correct paragraph ID returns 2 because it is not an exact substring of that registered paragraph;
5. **schema fail-closed control**: removing explicit metric identity blocks a reported decision, a question/schema-only amendment resolves it and changes the hash, and old decisions cannot silently carry over.

Expected error lines printed by the negative tests included:

```text
ERROR: F_YIELD_120C: candidate rejected by acceptance tests: F_YIELD_120C::required_condition
ERROR: F_YIELD_120C: quote is not an exact substring of the registered paragraph
ERROR: F_YIELD_120C: unresolved contract axes: metric_identity is not explicit in target schema
ERROR: adjudication is not bound to the current precompiled contract hash
```

These `ERROR:` lines are expected assertions inside passing negative tests; the suite's final result was `OK`.

## 4. Inspection boundary

The tests establish mechanical ordering, coverage, exact paragraph/quote/page binding, hash binding, fail-closed validation, and preservation of authored conflict/failure states. They do not prove general scientific correctness or prevent an agent from supplying a false semantic rationale. Original-source review remains necessary; the compiler intentionally performs no keyword selection or automated natural-language truth inference.
