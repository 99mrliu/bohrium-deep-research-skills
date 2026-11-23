# Synthetic run record

**SYNTHETIC EVIDENCE ONLY.** The inputs under `examples/synthetic-input` and `examples/invalid-input` are intentionally constructed examples, not formal challenge cases and not real experimental data.

## Environment contract

- Python: 3.10+ standard library only; no package installation required.
- Invocation root: skill root.
- Runtime paths shown here are relative; production defaults remain `/input/case.json`, `/input/task.md`, `/app/work`, `/app/output`.
- Outputs contain no wall-clock timestamp and no machine absolute path.

## 1. Synthetic clean + machine final check

```bash
python3 scripts/contract_auditor.py run \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work examples/synthetic-work \
  --out examples/synthetic-output
```

Observed exit: `0`.

The input has 8 rows. Output coverage is `kept=1`, `flagged=6`, `deduplicated=1`, `rejected=0`, `total=8`. Main findings represented in the output are:

- `MALFORMED_NUMBER` for `12..5`; normalized value remains null.
- `UNKNOWN_UNIT` for `furlong`; normalized value/unit remain null.
- `EXACT_DUPLICATE_REMOVED` for the second `EXT-001` extraction; `duplicate_of=R000001`.
- `MISSING_VALUE` for `N/A`; null is not imputed.
- `DUPLICATE_ID_CONFLICT` for two different `EXT-006` rows; both remain separate.
- `UNMAPPED_COLUMN` for `Lab Note`; values are retained under `unmapped__lab_note`.
- `quality_grade` and `future_extension` are null and listed in `unresolved_fields`.

`result.json.status` is `partial`, as required by open scientific/schema findings.

## 2. Independent verification

```bash
python3 scripts/contract_auditor.py verify \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --out examples/synthetic-output
```

Observed exit: `0`; `validation.json.status=pass`; summary `blocking=0,error=0`. The fresh-read verifier checked contract fields, null extension keys, manifest/checksums, row count, per-cell rebuild, source hashes, coverage, anomaly reconciliation, change log, and status consistency.

## 3. Deterministic second run

The same run command was executed into a temporary second work/output pair. `diff -r` against `examples/synthetic-output` returned `0`; all ten fixed artifacts were byte-identical.

| artifact | bytes | SHA-256 |
|---|---:|---|
| anomalies.csv | 1595 | 762791e93175f3b5ee31f9e17874535143a4ae5f1fdac8b478fc131f52d3f5db |
| audit.md | 2578 | 16bcb88e97161eb04df0d5e4b88fada90971682d97563abf2e7eeaa8fe6eb516 |
| changes.jsonl | 16154 | 79ad213137e424c6353fd621f78700e87c7ab7811c7a50f300f66901c38c8d29 |
| checksums.sha256 | 553 | abe58f70cd7c3932ad8a27d51a2bfef2be14ebfc8a65fe48ebeb3792cee1926a |
| cleaned.csv | 1925 | ca5052377300ab20bc49b0a83d7e09c6a9bf3eef56558c84aad519b6ae1f139b |
| cleaned.json | 5946 | f8e61713cf4e433169243abed4bf7f27d8c8e3862e1e715e4144cb4fac913add |
| manifest.json | 1791 | 2d38fa3d32e9512040264422862cb6e47476723b12196adc82f06dddbbbfe9f0 |
| result.json | 28824 | ab27d5543a151bf702d87b867c9ad249517a5f985540100a8c7396dcd53eec6e |
| review_queue.csv | 1824 | b93aac1beeb0fb55e2e8413745284c38938e4a853209a1f2111ac5f9284fb20d |
| validation.json | 2866 | 14882dc913b1402c041b9a10c06b7700ada7b3df489464b93fba2fd6b33c7acc |

## 4. Invalid input path

```bash
python3 scripts/contract_auditor.py run \
  --case examples/invalid-input/case.json \
  --task examples/invalid-input/task.md \
  --work examples/invalid-work \
  --out examples/invalid-output
```

Observed exit: `2`. The malformed JSON did not crash the process. It produced an empty statistical table, anomaly/review files, manifest, audit, and `result.json.status=input_error`.

Independent verify of that partial output returned `0` with `validation.json.status=pass_with_findings`, demonstrating that an honest input failure can itself have a structurally valid, reviewable partial delivery.

## 5. Deliberate corruption proof

A temporary copy of the valid synthetic output was modified by changing one cleaned value (`101325` to `999999`). The corrupted copy was used only for the test and is not part of this bundle.

```bash
python3 scripts/contract_auditor.py verify \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --out <temporary-corrupted-output>
```

Observed exit: `3`; `validation.json.status=fail`; blocking codes included both `ARTIFACT_CHECKSUM_DRIFT` and `RAW_CONVERSION_TRACE_BREAK`. This proves that checksum drift alone is caught and that semantic raw-conversion consistency is checked independently rather than trusting hashes alone.

## 6. Contract adapter checks

Direct standard-library checks passed for all three supported contract shapes:

- dict with `properties` plus `required`;
- list containing strings and `{"name": ...}` descriptors;
- comma/newline-delimited string with type annotations.

Unit disambiguation checks also passed: `C -> °C`, `M -> mol/L`, `metre -> m`.

## 7. Additional failure-path checks

- A nonexistent case path returned `2`, still produced all ten fixed artifacts, and independent verify returned `0` with an honest `input_error` partial result.
- A temporary `--max-rows 2` run returned `0` and verified successfully when `verify --max-rows 2` used the same budget. Coverage remained `total=8`, with `kept=1`, `flagged=1`, `rejected=6`, and exactly six `BUDGET_EXCLUDED` findings; no rows disappeared silently.
- Final syntax check passed without creating `__pycache__`. Final independent verification of both retained output sets returned `0`.
