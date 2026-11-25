# Runtime, schemas, and output contract

## Runtime layout

The production command is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/compare_estimands.py \
  --input /input --work /app/work --output /app/output
```

The agent reads `/input/case.json`, `/input/task.md`, `/input/comparison-workorder.json`, and every file under `/input/corpus/`. It writes the evidence-backed normalized records to `/app/work/estimands.json`, then runs the script. The script rejects corpus declaration mismatches, so an unlisted corpus file cannot be silently ignored. Final artifacts are `/app/output/comparison-matrix.md`, `/app/output/comparison-operations.md`, and `/app/output/result.json`.

Only the Python standard library is used. No service, upload, credential, installation, or network access is needed.

## case.json

Required fields:

```json
{
  "case_id": "exact-case-id",
  "corpus_documents": [
    {"source_document_id": "paper-a", "path": "corpus/paper-a.md"}
  ],
  "output_contract": {
    "comparison_matrix": "",
    "comparison_operations": "",
    "status": "",
    "sources": [],
    "uncertainty": [],
    "change_records": []
  }
}
```

Every actual file under `corpus/` must be declared exactly once. Paths are relative and may not escape the input root. The embedded ID must equal the declaration ID.

## Corpus text format

The first nonempty line is `SOURCE_DOCUMENT_ID: <id>`. Every subsequent nonempty line is one source paragraph in the form `[paragraph_id] exact paragraph text`. IDs may contain letters, digits, underscore, dot, colon, and hyphen. The parser preserves the paragraph text after the marker. Duplicate IDs and unmarked text are errors.

This intentionally small fixture format makes exact evidence testable. In a runner that extracts other document formats into this representation, preserve the original `source_document_id`, stable paragraph IDs, and exact text.

## comparison-workorder.json

Required fields are `case_id`, `task_id`, `operation_requests`, and `completion`. `task_id` must occur verbatim in `task.md`. Each operation request contains:

- unique `operation_id`;
- `operation`: DESCRIBE, DIRECTION, RANK, TRANSFORM, or POOL;
- nonempty unique `estimand_ids` referring to normalized records;
- optional `caveats` (mandatory and nonempty for DIRECTION);
- optional `transforms` for quantitative operations;
- optional `exchangeability` for POOL (all four required fields are needed to pass).

`completion` contains the booleans `all_documents_reviewed`, `all_requested_operations_evaluated`, and `all_output_contract_fields_addressed`. These are work assertions, not comparability assertions.

## work/estimands.json

The wrapper repeats `case_id` and `task_id`, then has a nonempty `records` list. Every record requires:

```json
{
  "estimand_id": "stable-id",
  "source_document_id": "paper-a",
  "task_id": "task-id-from-workorder",
  "outcome": "normalized outcome",
  "metric": {"name": "metric_name", "definition": "precise metric definition"},
  "population": "normalized study population or specimen set",
  "material": "normalized material",
  "pollutant": "normalized pollutant",
  "intervention": "normalized intervention/method",
  "condition": "normalized condition",
  "budget": {"value": 90, "unit": "min"},
  "time": {"value": 90, "unit": "min"},
  "unit": "%",
  "scale": "percentage points on closed interval [0,100]",
  "estimate": {"value": 92, "unit": "%", "direction": "decrease"},
  "evidence": [
    {"source_document_id": "paper-a", "paragraph_id": "p2", "quote": "Exact contiguous source text."}
  ]
}
```

Use the literal string `not_reported` for both `value` and `unit` when a measurement is absent. Do not substitute null, zero, or another study's value. Optional extra keys such as `moderators` may be retained; core dimensions remain required. Evidence quotes must be nonempty exact substrings of the cited paragraph and their evidence `source_document_id` must exactly match the record. This prevents a valid-looking quote from being attached to the wrong source/paragraph.

A transform item has `estimand_id`, `field` (`time` or `budget`), `conversion` (`min_to_h` or `h_to_min`), and a nonempty `reason`.

## Output contract and dynamic fields

The result contains exactly the top-level `case_id` plus every key in the original `output_contract`, without dropping unknown keys or adding convenience fields. `case_id` is copied exactly from `case.json` and verified after writing.

Output-contract values are type templates and are treated as input, never as schema instructions from source documents. Recognized names are matched case/punctuation-insensitively:

- comparison matrix: `comparison_matrix` or `matrix`;
- operations: `comparison_operations` or `operations`;
- `status`, `sources`, `uncertainty`/`uncertainties`, `change_records`/`changelog`;
- `operation_results`, `strata`/`stratum_register`, `estimands`/`estimand_register`.

String contract fields receive paths/status strings. List templates receive lists. Dict templates receive natural dictionaries or `{ "items": [...] }` for list-valued content, preserving the requested broad type. Unrecognized keys remain present: list becomes `[]`, dict structure is recursively preserved with empty values, string becomes `""`, and other scalar types become `null`. Each unmapped key creates `UNMAPPED_CONTRACT_FIELD` uncertainty and status `partial` because content was not invented.

The matrix includes preflight checks, every declared document, all normalized records, exact source IDs and paragraph IDs, exact quotes, and the raw stratum register. Operation results include allowed/blocked rationale, caveats, reasons, fingerprints, and exact transform audits. `sources` covers every corpus document with its SHA-256 and paragraph IDs. `uncertainty` records explicit unknowns, blocked gates, and incomplete/unmapped work. `change_records` lists actual generated files and hashes for the two Markdown artifacts; the source records are not edited.

## Local example and negative validation

From the bundle root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_example.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

The test named `test_negative_fake_pooling_fails_strict_mode` demonstrates that a fake A/B pooling request is blocked and raises `OperationBlocked` in strict mode. Ordinary example execution succeeds because blocked noncomparable operations are valid comparison findings, not incomplete work.
