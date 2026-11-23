# Synthetic contract-auditor example

**SYNTHETIC EXAMPLE ONLY — not a formal case and not real experimental data.**

Clean the nested JSON records and the declared CSV file, preserve missing values as null, do not merge conflicting IDs, and deliver all fields declared in `case.json.output_contract`.

The extra contract keys `quality_grade` and `future_extension` intentionally have no deterministic adapter; they must remain null and appear in `unresolved_fields`.

Example invocation from the skill root:

```bash
python3 scripts/contract_auditor.py run \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work examples/synthetic-work \
  --out examples/synthetic-output
python3 scripts/contract_auditor.py verify \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --out examples/synthetic-output
```
