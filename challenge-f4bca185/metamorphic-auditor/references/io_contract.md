# Input, lineage, and output contract

## Runtime contract

Run with Python 3 standard library only:

```sh
python3 scripts/metamorphic_auditor.py \
  --input /input --work /app/work --output /app/output
```

Optional `--case PATH` and `--task PATH` select case/task JSON or text. A relative path is resolved normally, then relative to `--input` if needed. `--verify-existing` disables generation and requires existing candidate artifacts in `--output`; raw inputs are still mandatory and reloaded. The work directory is scratch only and is never evidence or run state. There is no network access, clock field, random seed, or nondeterministic output dependency. Successful verification exits 0, process-verification failure exits 1, and input errors exit 2; all modes attempt all required report artifacts.

## Case/task discovery

Without explicit flags the tool tries `case.json`, `task.json`, `case_info.json`, `input.json`, `case.md`, `task.md`, `case.txt`, and `task.txt`. Case and task objects may be wrapped as `case`, `task`, `config`, or `payload`. JSON embedded as a JSON string or one fenced JSON block in text is recognized. Plain text still supplies `task_text`; simple `case_id: ...` lines are recognized. A missing, malformed, or unrecognized case/task is an input error rather than an invented case ID.

`case_id` falls back to `task_id`, `id`, then `challenge_id`. Supported optional normalization declarations are:

```json
{
  "unit_conversions": [{
    "id": "C_TO_K", "source_field": "temp_C", "target_field": "temp_K",
    "factor": "1", "offset": "273.15"
  }],
  "dedup": {"enabled": true, "keys": ["doi"], "context_keys": ["source_context"]}
}
```

Factors and offsets are decimal, with candidate `target = source * factor + offset`. There is no automatic unit ontology. Dedup is exact, normalized full-row equality inside key and context, never approximate bibliographic matching.

## Materials and common wrappers

CSV and TSV require a unique header and use the `csv` module. JSON may be a list, one object, or an object with a list under `materials`, `records`, `rows`, `items`, `documents`, `papers`, `entries`, `results`, `data`, `payload`, `content`, or `body`. The case itself may embed records under `records`, `rows`, `items`, `extractions`, `observations`, or `data`; arbitrary configuration objects and material-path lists are not promoted to observations. JSONL accepts one such value per nonblank line; each expanded item receives a deterministic 1-based data-row locator. Nested non-tabular values are serialized as canonical JSON cell text. Duplicate JSON keys and non-finite JSON numbers are invalid.

Each source row gets `_source_id`, `_source_file`, `_source_row`, and `_disposition`. These enable conservation and review. Candidate columns precede lineage columns; all original columns are retained. Candidate generation happens only when both cleaned CSV and JSON are absent outside verify-existing mode. Pre-existing candidates are audited, not overwritten.

## Output contract projection

`result.json` always includes `case_id`, `status`, `verification_status`, `sources`, `uncertainty`, `change_records`, `review_queue`, and `artifacts`. The eight artifacts are:

- `cleaned.csv`
- `cleaned.json`
- `verification.json`
- `counterexamples.jsonl`
- `changes.jsonl`
- `review_queue.csv`
- `audit.md`
- `result.json`

The audit writes an early `result.json` checkpoint before material parsing and again after case discovery. Final artifacts have relative paths and hashes; `result.json` intentionally has no self-hash.

For `output_contract` supplied as a dict, list, string, or wrappers (`fields`, `properties`, `outputs`, `artifacts`, `files`, `required`), every named field is projected to the top level of `result.json`. Recognized artifact names map to the eight artifacts; `cleaned_data`/`records`/`rows`/`data`, `change_log`, count, and summary requests receive actual reloaded payloads or computed counts. Unknown names remain JSON null, force honest partial delivery, and are listed in `unresolved_output_contract_fields`; the auditor never invents compliant content.

`review_queue.csv` ranks every failure and every review-required derivation/exclusion. Blocking impact precedes severity, with stable tie-breaking. All blocking rows and one deterministic representative of each other check form `minimal_audit_sample=yes`. If there are no failures or reviewable changes, one deterministic raw-row spot-check keeps the sample non-vacuous. This is a process audit sample, not statistical acceptance sampling and not a scientific adjudication sample.
