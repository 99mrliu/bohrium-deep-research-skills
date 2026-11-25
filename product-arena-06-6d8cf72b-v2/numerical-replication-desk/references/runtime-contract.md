# Runtime contract and status policy

The runner reads only the supplied case/task/material paths, standard-library files, and explicitly named original image artifacts. `run` defaults to `/input/case.json`, `/input/task.md`, `/input/materials`, and `/app/output`.

## Contract audit

Before any ledger execution or output writing, the runner audits the actual case's `output_contract` recursively. It checks:

- root object with a required string `case_id`;
- explicit object `properties`, `required`, and `additionalProperties: false` at every object level;
- supported nested types (`object`, `array`, `string`, `number`, `integer`, `boolean`, `null`, and typed unions);
- arrays with item schemas, `minItems`/`maxItems`, and boolean `uniqueItems`;
- `const` and `enum` using JSON-aware recursive equality (so `true` does not equal `1`, arrays/objects are compared recursively, and numeric `1` equals `1.0`);
- string `minLength`/`maxLength` and stdlib regular-expression `pattern`;
- finite numeric `minimum`/`maximum`, `exclusiveMinimum`/`exclusiveMaximum`, and positive `multipleOf`;
- nonempty `anyOf`/`oneOf`, and internal JSON Pointer `$ref` through `$defs` or `definitions`. References/combinators may have annotation fields but no constraint siblings; circular and external references are rejected.

Every other schema keyword is rejected explicitly rather than ignored. The writer emits exactly the declared property keys, initializes `const` fields from their declared JSON value, and recursively rejects extras, missing fields, wrong types, invalid const/enum/alternative/reference values, nonunique items, pattern failures, and size/numeric-bound violations. Optional declared fields are still included by the conservative partial-response skeleton so the result contains all contract fields. A response overlay may fill these fields but cannot introduce new ones. Contract audits and validation results are written in verification artifacts after a successful preflight; malformed contracts or results exit 2 without a success result.

## Recognized result fields

Fields named `case_id`, `numerical_findings`, `sources`, `uncertainty`/`uncertainties`, `change_records`, `artifacts`, `verification`, and `status` receive engine data when their schema shapes permit. Other fields, including direct-answer fields, come from `--response`; absent content stays an explicit `not_reported` string or empty collection. A synthetic case may supply an inline response for its deterministic QA workflow.

Logical completion is `complete` only when a response is supplied and no calculation mismatch, anchor failure, conflict, or source failure exists. The emitted status must be declared by that particular schema: `complete` is used when allowed, otherwise `success`; partial work requires `partial`, and total failure prefers `failed` with `partial` as fallback. If the schema permits no honest value (for example, only `success` while work is incomplete), result generation fails instead of forcing an incompatible or misleading status. Total failure includes cases where every calculation is uncomputed or failed closed because its anchors are unavailable/unverified. Original visual status is recorded independently so an unavailable original is not falsely called an arithmetic mismatch. Malformed inputs and fatal contract errors exit 2 without pretending success.

## Evidence and failure distinctions

Source records distinguish `readable`, `missing`, and `unreadable`. Missing optional documents and unreadable optional images do not become empty successful sources. Missing operands fail the affected calculation with an explanation. `not_reported` means a supplied source does not report the value; `missing` means the required input/source itself was not supplied. Neither means zero or independently calculated. In particular, a referenced but unsupplied original figure and its render/crop/review use `missing`.

`verification.json` keeps raw and rounded results, expected/tolerance comparisons, input anchors and exact region offsets, quote/locator checks, formulas, reconciliation conflicts, source states, contract audit, and visual status. Quotes are checked only at their declared region; legacy anchors are explicitly `locator_not_checked`, and bad or unchecked anchors fail dependent numerical claims closed. `change_records` lists extraction, calculation, source, conflict, and artifact actions so uncertainty survives into the final result.
