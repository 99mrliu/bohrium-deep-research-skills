# Dynamic response and cell format

The two scripts do not infer scientific answers. `plan_workorder.py` exposes the case-specific questions and exact contract; the agent reads sources and authors the response plan, `agent-response.json`, and `common-cells.json`. `assemble_response.py` validates those authored objects and renders their content.

## Contract introspection

Accepted `output_contract` forms include:

```json
["direct_answer", "limitations"]
```

```json
[
  {"name": "direct_answer", "type": "object"},
  {"key": "limitations", "type": "array"}
]
```

```json
{
  "direct_answer": {"type": "object", "description": "Case-specific definition"},
  "limitations": "Explicit unresolved limits"
}
```

Wrappers `{"fields": ...}` and JSON-Schema-like `{"properties": ...}` are also accepted. List field objects may identify a key by `name`, `key`, `field`, `output_key`, or `id`. Keys remain literal and case-sensitive. All named keys must appear under response `fields`, including keys whose truthful value is `not_reported` or noncomparability. Types, when declared, may be `string`, `number`, `integer`, `boolean`, `array`, `object`, `null`, or a list of these. Extra response fields are retained.

## Agent response object

```json
{
  "fields": {"the_exact_contract_key": {}},
  "completion": {
    "requested_work_complete": true,
    "read_failures": [],
    "fatal_failure": false
  },
  "uncertainty": [],
  "change_records": []
}
```

Optional `status` may be declared, but must agree with derived status. `fatal_failure: true` yields `failed`; incomplete requested work or a nonempty `read_failures` list yields `partial`; otherwise status is `success`. The script never downgrades merely because values are absent from sources or cannot be compared.

`change_records` should be short, case-specific objects or strings documenting transformations, unit conversions, exclusions, unresolved reads, and important response decisions. It is not a replay log of generic processing steps.

## Document and evidence objects

`documents` must exactly match the workorder's in-scope IDs. Each entry is:

```json
{"source_document_id": "exact-id", "path": "relative/tagged-source.txt"}
```

Paths must stay under `--source-root`. Text uses one `[paragraph_id]` marker per paragraph. A cell always has `cell_id`, `question_id`, `dimension`, `source_document_id`, `paragraph_id`, `state`, and `value`. A `reported` cell also has a contiguous `quote` found in that exact paragraph after whitespace normalization. A non-reported state needs no invented quote.

Use any question-specific dimensions and metadata needed by the workorder. Six reserved comparability attributes—`task`, `metric`, `units`, `material`, `pollutant`, and `budget`—are required on every member of a quantitative synthesis. Other useful attributes such as `dataset`, `time_point`, `dose`, or `page` can be added freely.

## Syntheses and exclusions

A qualitative synthesis needs `synthesis_id`, `member_cell_ids`, and `statement`; set `kind` to `qualitative` or omit it. A quantitative synthesis additionally requires at least two distinct member cells, all six `comparability_checks` set to true, numeric member `value`s, matching result `units`, and truthful member metadata. `method: arithmetic_mean` is checked numerically. Other quantitative methods require `result`, explicit method/formula detail, and agent verification.

An exclusion retains evidence without pooling it:

```json
{
  "cell_ids": ["document-c-performance"],
  "state": "noncomparable",
  "reason": "The pollutant differs; do not calculate a shared mean."
}
```

A completed exclusion is a scientific answer, not a processing failure.

## Rendered outputs

- `comparison-matrix.md` contains document coverage, only the authored evidence dimensions, source spans, comparability metadata, and retained exclusions.
- `integration-report.md` presents each exact contract field as a requested response, followed by any authored syntheses, exclusions, uncertainty, sources, and change records.
- `result.json` starts with the agent's dynamic fields and adds standard metadata. `sources` is derived from validated cell locators. To prevent silent overwrites, agent fields may not use the reserved metadata keys `case_id`, `status`, `sources`, `uncertainty`, or `change_records`.
