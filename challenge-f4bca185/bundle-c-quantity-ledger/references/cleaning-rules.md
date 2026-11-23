# Cleaning rules, priorities and conflict order (quantity-ledger)

Rule ids appear in `change_log` / `conversion_ledger`; ids are stable across
runs of the same version.

## Rule registry (id → meaning)

| id | action | failure mode |
|---|---|---|
| `SCHEMA.alias.<field>` | raw column label renamed to canonical field via `aliases.json` | two columns → same canonical field with different values: `alias_conflict` review, second column kept in `extra` |
| `SCHEMA.range_fields` | `value_low`+`value_high` joined into a range literal | one bound missing → not joined, value stays missing |
| `LEX.embedded_unit` | unit split out of the value cell when the unit column is absent | split only on `<numeric> <rest>` pattern, else raw kept |
| `LEX.plus_minus` / `LEX.parenthesis_last_digits` | symmetric uncertainty split into its own field | never rewritten into a range |
| `LEX.range` | range parsed to low/high | `low > high` → `invalid_range_order` |
| `P.*`, `U.*`, `U.power^<n>` | SI prefix / unit symbol / power rule from `units.json` | unknown or ambiguous symbol → review |
| `UC.affine_linear` | composed conversion `std = raw × multiplier + offset` | dimension mismatch → `incompatible_target_unit` |
| `DEDUP.conservative_key` | duplicate flag on identical normalized key | flags only; never merges |

## Processing order per record

1. Alias normalization (`SCHEMA.alias.*`). Collisions → review, no overwrite.
2. Value assembly: `value_low`+`value_high` → range literal; embedded unit split.
3. Number parse (grammar in `lexical-grammar.md`). Any rejection → anomaly +
   review, raw preserved, record status `review`.
4. Unit parse + conversion to per-metric `target_units` override, else default
   SI target. Unknown/ambiguous/incompatible → raw kept, review.
5. Sanity rules (e.g. `negative_absolute_temperature`).
6. Cross-record pass: duplicate flagging.

## Duplicate key (conservative by construction)

`(material lowercased+trimmed, normalized metric, standardized value or raw
value + unit, range bounds, uncertainty, conditions incl. source locators)`
— all fields must be present and identical. Records with missing material,
metric or value are never flagged. Flagged groups get `duplicate_group=DUPnnn`
and a review item; **no row is dropped or merged automatically**, because a
repeated experiment and a repeated extraction are indistinguishable to the
tool. Cross-paper matches are expected and must be adjudicated by a human.

## Anomaly taxonomy

`missing_value`, `malformed_number`, `ambiguous_decimal_comma`,
`unknown_unit`, `ambiguous_unit`, `affine_in_composite`,
`incompatible_target_unit`, `invalid_range_order`,
`encoding_replacement_char`, `negative_absolute_temperature`,
`missing_material_file`, `malformed_material_json`, `empty_table`,
`no_records_found`. Every anomaly also opens a review item; review items also
cover `missing_unit`, `alias_conflict` and `duplicate_group`.

## Status semantics (honest reporting)

- `success`: records ingested, zero anomalies, zero review items, no
  unresolved contract keys.
- `partial`: anything needed human judgment, no records found, or contract
  keys could not be filled (`null` + `unresolved` list).
- `input_error`: case file unreadable / malformed JSON / rule resources
  unreadable. A minimal result.json exists in every case (it is written before
  ingestion starts).
