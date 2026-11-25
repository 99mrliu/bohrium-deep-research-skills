# Dynamic result contract and finalization

## Extracting the contract

`verify_case.py` and `finalize_result.py` read a JSON fenced block in `task.md` containing `output_contract` (or a direct contract), with a case-level contract as fallback. Contract discovery is dynamic; do not hardcode the field set for a new task.

Supported contract forms include:

```json
{
  "required_fields": ["case_id", "status", "answers", "artifacts"],
  "field_types": {
    "case_id": "string",
    "status": "string",
    "answers": {
      "type": "object",
      "required_fields": ["claim_assessment", "limitations"],
      "field_types": {"claim_assessment": "string", "limitations": "string"}
    },
    "artifacts": {"type": "array", "items": {"type": "string"}}
  },
  "status_enum": ["complete", "partial"]
}
```

`fields`/`properties`, `required`/`required_fields`, nested object schemas, array items, enum/const, simple unions, and basic numeric/string bounds are also understood. Every declared field is emitted, not only required fields. `case_id` is always copied exactly from the case. Status is selected from `status_enum`; common complete/partial synonyms are recognized without emitting a value outside the enum. A task should include a partial status so that insufficient evidence has an honest representation.

## Two-stage result

1. The verifier immediately writes an early partial result with the exact case id and every declared output field. If parsing/evaluation subsequently fails, `analysis.json` records the error and no number is imputed.
2. After evaluation it writes `analysis.json`, `report.md`, sweep CSV/optional PNG files, and a still-partial draft `result.json` with available analysis fields and artifacts.
3. The agent reads the analysis and authors the substantive answers. The finalizer consumes those answers rather than generating them. It combines canonical source/fault verdicts, validates the supplied artifacts and all dynamic fields, and writes the final result.

Example:

```bash
python3 scripts/finalize_result.py \
  --case /input/case.json --task /input/task.md \
  --analysis /app/work/analysis.json \
  --answers /app/work/agent_answers.json \
  --artifacts /app/work/analysis.json /app/work/report.md \
  --output /app/output/result.json
```

If the contract has direct agent-answer fields rather than a single `answers` object, matching top-level keys from the authored answers JSON populate those fields. Artifact entries are paths by default, or a filename-to-path object when the contract requests an object. Every referenced path must exist as a file. Failed validation writes `finalization_errors.json`, returns a nonzero exit code, and restores an honest partial result instead of inventing required answers. A missing nested answer, incorrect field type, out-of-enum status, mismatched case id, empty answer object, empty artifact collection, or nonexistent artifact blocks completion.

The finalizer derives `complete` versus `partial` from the retained analysis. A complete run may still have an inconsistent source claim or failed invariant: this means the evidence sufficed to identify a discrepancy, not that the claim is correct. No properties, unresolved inputs/claims, or unevaluated properties force partial status. Deliberately undetected injected faults are reported diagnostically; they indicate a weak test suite and should be discussed in agent-authored limitations rather than misattributed to the source.

## Synthetic example inspection

Run `bash examples/run_synthetic_example.sh`. It creates a unique external temporary work directory, prints exact output paths, asserts the final source/fault/property outcomes, and leaves the runtime PNG outside the bundle for inspection. Plotting is optional; JSON, Markdown, and CSV remain valid when PNG is unavailable. No example output or binary belongs in the skill bundle itself.
