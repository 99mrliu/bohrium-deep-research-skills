# Mapping and cleaning rule catalogue

All rules are numbered, ordered and editable. The field dictionary
(`field-dictionary.json`) and unit table (`units.json`) are the data behind these rules;
this document is the contract for how they interact. Bump `schema_version` when rules or
canonical fields change and log the migration in `types-and-migration.md`.

## Rule priority (highest first)

| order | rule | scope | condition | effect | failure mode |
|---|---|---|---|---|---|
| 1 | INGEST-JSON / INGEST-CSV | source | list-of-objects JSON nodes; headered CSV strings/files | harvest rows with source id + locator | unreadable CSV file → warning, skipped |
| 2 | MAP-001 exact alias | column | normalized header == normalized alias (NFKC, casefold, punctuation → `_`) | confidence 0.99 | none (deterministic) |
| 3 | MAP-002 `_UNIT` suffix | column | header stem is an exact alias **and** the trailing token is a known unit of that field's dimension | confidence 0.92, unit hint from suffix | unit token unknown → rule does not fire |
| 4 | MAP-004 component | column | alias match plus min/max/low/high/下限/上限 convention | maps to one range endpoint; both endpoints composed, never averaged | component on non-numeric field → rejected |
| 5 | MAP-005 unit disambiguation | column | tied top candidates; header unit hint resolvable in exactly one candidate's dimension | +0.05, tie broken | both/neither resolve → stays ambiguous |
| 6 | MAP-003 stop-word fuzzy | column | alias plus only stop-word tokens (`conditions`, `value`, …) | confidence 0.78 | requires MAP-TYPE-GUARD for numeric fields |
| 7 | MAP-TYPE-GUARD | column | fuzzy numeric match where column values are never numeric-like | candidate rejected | can push a column to unmapped (intended) |
| 8 | MAP-AMBIG | column | two candidates within 0.03 after MAP-005 | column left **unmapped**, high-severity review | — |
| 9 | TYPE-000..004 | column | see `types-and-migration.md` | semantic type with evidence | mixed columns keep kind counts |
| 10 | RANGE-SPLIT | cell | `a–b`, `a~b`, `a..b`, `a 至 b` … | low/high preserved, no midpoint invented | low > high → ANOM-RANGE-ORDER |
| 11 | UNIT-CONV | cell | unit resolvable in the field's dimension | `target = value*factor + offset`, 12 significant digits, formula logged | none |
| 12 | UNIT-CONFLICT | cell | header unit ≠ value unit (normalized) | no conversion, review | — |
| 13 | UNIT-UNKNOWN | cell | unit text not in unit table | normalized value null, raw kept, anomaly + unresolved-schema entry | extend `units.json` to resolve |
| 14 | (unit absent) | cell | numeric value without any unit | value kept verbatim, `unit=null`, `unit_missing` flag, uncertainty note | no default unit is ever assumed |
| 15 | MISS-001 | cell | missing token / null / column absent in row | value stays null, nothing imputed | — |
| 16 | ANOM-PARSE | cell | numeric field value unparseable | raw kept, null, anomaly | — |
| 17 | ANOM-OUT-OF-RANGE | cell | value outside dictionary `plausible_range` (same unit) | kept, flagged, never clipped | — |
| 18 | FIELD-COLLISION | row | two source columns map to one field with different values | first kept, review, both raws preserved | — |
| 19 | DUP-EXACT | row group | identical context key **and** identical measured values | `exact_duplicate_candidate`, medium review; nothing dropped | — |
| 20 | DUP-CONFLICT | row group | identical context key, different measured values | `context_value_conflict`, high review; **never merged** | human scientific adjudication required |
| 21 | CONTRACT | result | output_contract fields | known fields filled, unknown → null + `unresolved_contract_fields` | never fabricated |

## Conflict-resolution principles

1. **Specific beats fuzzy**: MAP-001 > MAP-002 > MAP-004 > MAP-003; ties go to humans (MAP-AMBIG),
   never to coin flips.
2. **Units are evidence, not decoration**: a resolvable unit hint disambiguates (MAP-005);
   an unknown or conflicting unit blocks conversion (UNIT-UNKNOWN / UNIT-CONFLICT) instead of
   being guessed.
3. **Literal arithmetic never replaces scientific judgment**: two rows with the same context but
   different values are a *conflict to report*, not a merge candidate, even after perfect unit
   normalization.
4. **Null is a result**: missing stays missing; the review queue — not the cleaned table — is the
   place for open questions.
