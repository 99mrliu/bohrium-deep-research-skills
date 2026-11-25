# Minimal runnable example — SYNTHETIC ONLY

This is not an official case, paper, expected answer, or benchmark. Every source sentence, subject, value, and claim is invented solely to exercise the validator.

From the skill directory:

```bash
python3 examples/minimal/run_example.py
```

No installation or third-party package is needed. Use Python 3.9 or newer. The example performs four concrete actions:

1. generates a valid synthetic result, targets, exact source corpus, and decoy review;
2. runs 14 isolated in-memory mutations and writes `audit-report.json`, including each mutation's actual rejection, expected-code observation, and base-integrity result;
3. serializes each corrupted copy under `corrupted/`, invokes `validate_result.py` in a separate process, and records the real nonzero exit status and actual error codes in `cli-rejections.json`; and
4. invokes the independent finalizer and verifies that its finalized valid result is byte-identical to the original valid base.

Console output has one line per mutation, for the form:

```text
wrong_subject: actual_pass=true validator_exit=1 expected_code=SUBJECT_MISMATCH
```

Here `actual_pass` means that the **rejection control behaved as expected**, not that the corrupted scientific value was accepted. Overall failure (a surviving mutant, wrong rejection code, changed base, failed finalizer, or unparseable validator output) makes the example exit nonzero.

Important files under the chosen output directory:

- `valid-result.json`: unmodified valid synthetic base;
- `audit-report.json`: in-memory base and mutation outcomes, hashes, and semantic limitation;
- `cli-rejections.json`: subprocess exit status and expected/observed codes for every corrupted copy;
- `finalized/result.json`: independent finalization output, checked byte-for-byte against the base;
- `case.json`, `target-fields.json`, `source-corpus.json`, `decoy-review.json`: synthetic run inputs;
- `corrupted/*.json`: invalid synthetic copies, never formal answers.

`INSPECTION.md` records the actual commands and observed outcomes for this delivered version. Structural and mutation acceptance still does not prove semantic correctness; a real case requires source-facing agent decoy review.
