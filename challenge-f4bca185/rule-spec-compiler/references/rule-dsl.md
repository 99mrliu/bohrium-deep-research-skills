# Declarative rule DSL

## Sources and provenance

Declarations can come from four explicit sources:

1. `case.json` keys: `rules`, `field_mappings`/`field_mapping`/`mappings`, `missing_tokens`/`missing_values`, `numeric_fields`, `numeric_conventions`, `range_fields`, `range_conventions`, `unit_targets`, and `identity_keys`/`row_identity_keys`.
2. `task.md`: a fenced block labeled `rule-spec` or `json rule-spec`, whose body is one rule, a rule list, or `{"rules":[...]}`. Labeled lines are also recognized for `missing tokens`, `numeric fields`, `range fields`, `identity keys`, `unit target: field = unit`, and `field mapping: old -> new` (Chinese equivalents are included in the implementation).
3. `--rules FILE`: an object with `rules`, a rule list, a single typed rule, or an object mapping declared IDs to rule objects. Without `--rules`, `rules.json` and case-listed `rule_resources` are discovered.
4. `--config FILE`: additions/overrides described below.

Every normalized rule carries `provenance: [{source,pointer}]`. Case pointers are JSON Pointers; task pointers refer to lines. Identical semantic declarations receive the same stable content-based ID and merge their provenance. There is no global dictionary-derived cleaning rule: built-ins run only when one of these sources explicitly declares them.

## Common keys

| Key | Meaning |
|---|---|
| `type` | Operation type (aliases such as `numeric`, `range`, `unit`, `rename` are normalized) |
| `id` | Optional human-readable declared ID, useful for overrides |
| `priority` | Integer; lower executes first; defaults are listed below |
| `enabled` | `false` holds a declaration; absence means enabled after compile checks |
| `field` | Target column; `*` means all columns where supported |

The `rule_id` is derived from normalized semantics and type, not source ordering. `priority` participates in that semantic identity. `execution_order` in the plan is priority then rule ID, making ties deterministic.

## Operations

### `rename_field` — default priority 100

```json
{"type":"rename_field","source":"Dose Text","target":"dose_g"}
```

Unambiguous source aliases are compiled into downstream field references and identity keys. Occupied targets are never overwritten; a distinct nonempty value generates `FIELD_COLLISION`.

### `normalize_missing` — 200

```json
{"type":"normalize_missing","field":"*","tokens":["NA","N/A","未测"]}
```

Only listed tokens normalize to empty. Already empty and `null` values remain empty and are not logged as edits. A global declaration protects listed missing tokens from parsing and later conversions. No default NA-like vocabulary exists.

### `trim_whitespace` — 300

```json
{"type":"trim_whitespace","fields":["sample_id","note"]}
```

Trims leading/trailing Unicode whitespace only. It does not collapse internal whitespace or alter empty cells.

### `literal_map` — 350

```json
{"type":"literal_map","field":"sex","case_sensitive":false,"values":{"F":"female","M":"male"}}
```

Exact declared values map literally. Unmapped values pass through. With case-insensitive operation, declared map keys are case-folded.

### `regex_replace` — 360

```json
{"type":"regex_replace","field":"label","pattern":"^\\s+","replacement":""}
```

Uses Python standard-library `re.sub`; invalid expressions fail compilation. Both strings and explicit declaration are mandatory. This is a case-declared custom rule, not an implicit normalization.

### `parse_number` — 400

```json
{"type":"parse_number","field":"yield","decimal":".","thousands":",","allow_percent":false}
```

Returns canonical base-10 text using `Decimal`. A decimal comma or thousands separator must be explicitly declared. Ambiguous punctuation, units, non-finite numbers, and arbitrary numeric-looking strings are retained with `CONVERSION_ERROR`. Percent conversion is performed only when `allow_percent` is true.

### `normalize_range` — 420

```json
{"type":"normalize_range","field":"observed_range","decimal":".","thousands":","}
```

Canonicalizes two finite bounds to `lower..upper`. Recognized separators are `..`, ellipsis, en/em dash, spaced `to`, tilde variants, and hyphen. Reversed bounds are review items, not automatically swapped. A range and number rule on one field is an incompatibility, not a chained conversion.

### `convert_unit` — 440

```json
{"type":"convert_unit","field":"dose_g","target":"mg","decimal":".","thousands":","}
```

The unit must be attached to the value or explicitly supplied as `source_unit`. The output is a bare number in `target`; an absent or unknown unit is not guessed. The deliberately small conservative built-in arithmetic table covers consistent mass, length, volume, amount, and molar-concentration prefixes; it is not a vocabulary cleaning dictionary. Conversion uses `Decimal` and a ratio to the target unit. Incompatible dimensions generate review items.

### `validate_identity` — 900

```json
{"type":"validate_identity","keys":["sample_id","batch"]}
```

Builds review/change identity from declared keys and flags empty/all-empty and duplicate identities. Rows are never removed or merged. Multiple conflicting identity declarations are all held. Without identity keys, stable source-file and source-ordinal identity is used.

## Overrides and JSON Patch

A config object deep-merges `case` into the loaded case; top-level `rules` appends declarations:

```json
{
  "case":{"output_columns":["sample_id","yield"]},
  "rules":[{"id":"reviewed-precision","type":"parse_number","field":"yield"}],
  "disable_rule_ids":["R-parse_number-…"],
  "reviewed_rule_ids":["R-parse_number-…"],
  "rule_overrides":{"reviewed-precision":{"priority":395}}
}
```

If no `case` wrapper is present, remaining object keys are treated as case fields. `reviewed_rule_ids` documents review intent; a built-in still must be explicitly declared to run. `rule_overrides` is keyed by declared `id`, not array position.

A top-level array is interpreted as deterministic JSON Patch with `add`, `replace`, and `remove` on the root `{"case": {...}, "rules": [...]}`. Example:

```json
[{"op":"replace","path":"/case/output_columns","value":["sample_id","yield"]}]
```

Overrides are source-hashed and recorded in `sources` and the plan. Config parse/patch errors are never silently ignored.

## Output contract shapes

`output_contract` accepts a string list, a `{name,required}` object list, a direct field map, or a `fields`/`properties` + `required`/`optional` wrapper. Required and optional fields are emitted. Only actual records, statistics, counts, changes, plan, and standard result fields are resolvable. Unknown required values remain `null` and are placed in `unresolved_fields`.

For synthetic-only fixtures, `artifact_marker` adds a visible marker to all emitted record/metadata formats. It has no default and should not be set for official cases.
