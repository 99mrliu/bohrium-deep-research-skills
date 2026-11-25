# Declarative predicate and output schema

## 1. Evaluation model

A bank is a JSON object with an `items` array. Production downstream scoring and the example require exactly four unique, `required: true` items. Each item has an `item_id`, `status: "benchmark-DRAFT"` during authoring, source-backed `reference_answer`, `evidence`, a `rubric`, and a `probes` array for mutation testing. Evidence never substitutes for a predicate match.

A rubric has exactly these fields:

- `predicates`: nonempty array of `{id, category, predicate}`. IDs match `[a-z0-9_.-]+` and are unique within an item. Categories feed the failure taxonomy.
- `score_bands`: nonempty **ordered** array of `{score, when, rationale}`. `score` is integer 0, 1, or 2. The first matching band wins, so bands normally appear 2, 1, then 0. Rationale is mandatory.
- `default_score`: integer 0, 1, or 2; normally 0. It applies only when no band matches.

A band condition is a check ID string or a recursive object with exactly one of `all`, `any`, or `not`. `all`/`any` contain nonempty arrays of conditions; `not` contains one condition. Only those Boolean operators and registered check IDs are interpreted. There is no Python expression parser, `eval`, `exec`, import, function lookup, or arbitrary code execution.

Whitespace-only and malformed non-string candidates are forced to score 0 even if forbidden-only predicates pass. `score_engine.score_candidate` still returns every check's pass/fail state and reason. A malformed rubric is an input error, never a reason to invent correctness. Every successful candidate result has integer score 0/1/2, an item ID, rubric SHA-256, explicit checks, matched band or default, and score reason.

## 2. Predicate nodes

Every predicate node has exactly one operator. The generic result includes `passed`, `reason`, and recursive `details`. Composition evaluates all children, giving deterministic diagnostic traces rather than short-circuit omissions.

### Literal alternatives

```json
{"literal": ["NQ-7", "催化剂 NQ‑7"], "mode": "contains"}
```

`literal` is one string or a nonempty string array. `mode` is `contains` (default) or `exact`. Candidate and alternatives undergo Unicode NFKC, common dash unification (`−`, en/em/nonbreaking dashes to ASCII `-`), casefolding, and whitespace folding. `contains` means normalized substring; `exact` means the entire normalized output equals an alternative. Use `forbidden` for negation rather than assuming search order.

### Regex alternatives

```json
{"regex": ["\\bnot reported\\b", "未\\s*报告"], "flags": ["I", "M"]}
```

`regex` is one pattern or a nonempty pattern array. Patterns are NFKC-normalized, common-dash-normalized, and casefolded; only stdlib `re` flags `I`, `M`, and `S` are accepted. A search match of any alternative passes. Patterns are data and must be reviewed like other rules. Avoid nested ambiguous quantifiers.

### Composition and forbidden assertions

```json
{"all": [
  {"literal": "amber vial"},
  {"any": [{"literal": "sealed"}, {"literal": "密封"}]},
  {"not": {"literal": "4 °C"}}
]}
{"forbidden": [
  {"regex": ["未\\s*使用\\s*NQ-7"]},
  {"literal": "催化剂 NQ-3"}
]}
```

- `all` passes iff every child passes.
- `any` passes iff at least one child passes.
- `not` reverses its child.
- `forbidden` passes iff **none** of its children matches. Its failure reason identifies child indexes, making an asserted contradiction visible.

A forbidden check should have its own ID and category and must be included in appropriate score bands. Merely defining it does not automatically veto a band.

### Required-unit numeric comparisons

```json
{"numeric": {
  "target": 82.4,
  "units": ["%", "percent", "百分比"],
  "comparison": "eq",
  "require_unit": true,
  "tolerance": {"absolute": 0.05, "relative": 0}
}}
```

`require_unit` must be literal `true`; bare numbers cannot pass. `units` is a nonempty string/alternative array, normalized with the same text normalization and matched longest-first. Supported comparisons:

- `eq`: `abs(value-target) <= absolute + relative*abs(target)`;
- `lt`, `lte`: compare against `target + absolute + relative*abs(target)`;
- `gt`, `gte`: compare against `target - absolute - relative*abs(target)`;
- `between`: inclusive `min`/`max`, expanded by `absolute + relative*max(abs(min),abs(max))`.

For `between`, supply `min` and `max`; other comparisons supply `target`. All numbers must be finite JSON numbers. Both tolerance fields are mandatory and nonnegative, including explicit zeros. Any occurrence carrying a recognized unit that satisfies the comparison passes. Other numeric occurrences remain in diagnostics and can be handled by separate forbidden predicates. This scorer does not perform implicit unit conversion: list only units accepted without conversion, or add separately reviewed numeric rules.

Signed decimals and scientific notation are supported. ASCII-identifier boundaries reduce accidental matches inside names. Unicode minus signs are normalized before parsing.

## 3. Item and score-band example

```json
{
  "predicates": [
    {"id": "entity", "category": "entity",
     "predicate": {"literal": ["NQ-7"]}},
    {"id": "yield", "category": "numeric_value_unit",
     "predicate": {"numeric": {"target": 82.4, "units": ["%"],
       "comparison": "eq", "require_unit": true,
       "tolerance": {"absolute": 0, "relative": 0}}}},
    {"id": "no_reversal", "category": "forbidden_assertion",
     "predicate": {"forbidden": [{"literal": "未使用 NQ-7"}]}}
  ],
  "score_bands": [
    {"score": 2, "when": {"all": ["entity", "yield", "no_reversal"]},
     "rationale": "entity and required-unit yield are correct without reversal"},
    {"score": 1, "when": {"all": ["entity", "no_reversal"]},
     "rationale": "correct entity but missing/wrong required-unit yield"},
    {"score": 0, "when": {"not": "entity"},
     "rationale": "required entity absent"}
  ],
  "default_score": 0
}
```

The ordered bands and each check expectation are reviewed by a person. The engine does not decide that a match deserves 2.

## 4. Probe suite contract

Each item contains probes with exactly `probe_id`, `probe_class`, `raw_output`, `expected_score`, `expected_predicates`, and `rationale`. Expected predicates must cover exactly all current rubric IDs with Boolean values. Probe IDs must be globally unique. `mutation_check.py` executes independent classifications and exits 1 on score/predicate disagreement or missing classes, and 2 on unreadable/malformed bank JSON. It never auto-populates expected classifications from actual results.

`empty` probe raw output is a legitimate string `""`; this differs from `score_outputs.py`, where empty real output is refused unless `--allow-empty` is explicitly supplied.

## 5. Raw candidate and score report contracts

Candidate input is:

```json
{"outputs": [{"item_id": "item-01", "raw_output": "candidate text"}]}
```

Exactly the four required bank IDs must appear once. Unknown, missing, duplicate IDs, non-string output, JSON duplicate object keys, empty output, and over-limit output are refused. Empty/overlimit behavior can be changed explicitly with `--allow-empty`, `--max-chars N`, or `--allow-overlimit`; these switches do not alter predicate logic, and empty allowed output scores 0.

Each actual record includes raw output and `raw_output_ref: "sha256:..."`, rubric hash, individual check details, score rationale, and failure taxonomy. Rollup recomputes:

`score_total = sum(four required scores)`, `max_score = 8`, `required_denominator = 4`, `normalized_score = score_total / 8`.

No optional item enters the denominator. `finalize.py` rechecks IDs, scores, rubric hashes, raw traces, mutation pass, and the arithmetic. In non-strict mode a failed gate remains explicit `partial`; `--strict` writes that honest partial but exits nonzero.

`finalize.py` parses the case's explicit `output_contract` and binds every declared field at the result top level; arbitrary original case fields are metadata extras, not contract declarations. The unchanged original `case_id` is always top-level even when omitted from the contract. Supported declarations include name lists, `fields` name/object lists, direct field-to-type maps, `properties`, and `required_fields` / `required_top_level_fields`. Generated exports and strict gates also live under the reserved `rubric_mutation_lab` key, but that nested exporter does not replace any top-level field.

A declared unknown field is never guessed from case metadata: a required unknown becomes `null` with a failed gate. Missing reports produce honest typed empty containers where meaningful and leave the result `partial`. Strict completion requires non-null, type-compatible bindings for every contract field in addition to all item/scoring/mutation gates. Existing `sources`, `uncertainty`, and `change_records` are bound to their declared semantic fields and preserved in the nested export. This bundle never measures human agreement: contract fields receive an explicit not-measured object/note when their type permits, while an unavailable numeric score remains `null` rather than being invented as zero.

## 6. Known limits and mandatory manual review

This is an exact rule executor, **not English (or multilingual) semantic entailment**. Normalized literal/regex search can miss synonyms, coreference, inferred quantities, tables converted to prose, and nuanced modality. It can accept a correct-looking phrase in the wrong scope, negation, quotation, or entity context. Required-unit matching is not dimensional analysis or unit conversion. Any-of numeric matching can accept one correct number while another contradictory number is present unless separately forbidden. Regex can be overly broad or pathological; keep patterns simple and input limits enabled. “Not reported” means not reported in supplied material, not universal nonexistence.

Manually review when: a probe disagrees; a correct paraphrase fails; a wrong answer passes; scores depend on a new synonym; conditions or entity scope are ambiguous; multiple values conflict; units require conversion; source evidence conflicts; a legitimate unreported answer is penalized; a forbidden rule rejects an allowed contrast; or a mutation unexpectedly remains green. Do not “fix” such cases by copying actual scores into expected labels. Re-read source, revise the declarative rule or the independent label with a documented reason, then rerun twice.
