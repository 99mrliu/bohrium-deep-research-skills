# Runtime, outputs, and status

## Inputs and outputs

`run_case.py` reads these files when present:

- `case.json` (required): exact `case_id` and list- or dictionary-shaped `output_contract`;
- `task.md` (required): human task statement;
- `comparison-workorder.json` (required): comparisons and common fields;
- every `.txt` and `.pdf` file recursively under `input/`.

Other source extensions are ignored and recorded. Text decoding tries UTF-8 with BOM support and then UTF-8 strict; non-UTF-8 text is reported rather than silently corrupted. PDF extraction uses an existing `pdftotext -layout` executable. No packages are installed. Form feeds delimit page numbers; blank lines delimit paragraphs.

Default work files are `source-index.json` and `evidence.json` under `/app/work`. Final output files are:

- `matrix.json` and `matrix.md`: all indexed document/comparison rows, dynamic common fields, exact source IDs, and support paragraph IDs (`not_reported` or `missing_evidence_record` when no support paragraph is valid);
- `evidence-ledger.md`: accepted and excluded intervals, derivations, absence scopes, conflicts, uncertainty, and validation errors;
- `result.json`: exact `case_id`, requested contract fields, `status`, `sources`, `uncertainty`, and `change_records`.

## Output contract assembly

The assembler accepts an `output_contract` list, a dictionary containing `fields` or `required_fields`, or a direct field-to-specification dictionary. List entries can be names or objects with `name`, `field`, or `key`. Specification types guide empty placeholders. Common aliases for matrix, synthesis, limitations, and comparison scope are supported.

Every unknown requested field is retained with an empty value and an uncertainty entry; it is never silently dropped. `case_id`, `status`, `sources`, `uncertainty`, and `change_records` are always present even if omitted from the contract.

## Status

- `success`: indexing and validation completed, every document/comparison has valid evidence, all requested fields have producers. `not_reported` and `noncomparable` are compatible with success.
- `partial`: some valid rows exist but records were excluded, coverage is missing, sources were unreadable, or an unregistered contract field was requested.
- `failed`: a fatal input/index error occurred, or no valid evidence row could be rendered.

Validation writes outputs before returning a nonzero exit code when status is not successful. This preserves an auditable failure artifact. A process exit of 0 means success; 2 means honest partial/failed completion; 1 means the result artifact itself could not be produced.
