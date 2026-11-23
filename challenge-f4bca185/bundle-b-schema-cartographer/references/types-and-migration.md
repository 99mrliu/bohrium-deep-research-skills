# Semantic types and schema migration

## Semantic types (column profile level)

Each (source, header) column gets exactly one inferred type with rule-coded evidence
(`type_evidence.rule` in the mapping report):

| type | rule | inference criteria (on non-missing values) |
|---|---|---|
| `missing` | TYPE-000 | every value is null or a dictionary `missing_tokens` entry |
| `range` | TYPE-004 | ≥60% match range syntax (`a–b`, `a~b`, `a..b`, `a 至 b`, …) |
| `numeric` | TYPE-003 | ≥80% parse as numbers (optional ± uncertainty, trailing unit) or ranges |
| `identifier` | TYPE-002 | ≥90% unique, identifier-shaped tokens (no spaces), id-like header or values |
| `string` | TYPE-001 | fallback free text |

The profile also keeps full `kind_counts`, `uniqueness` and up to 5 samples, so reviewers can
check mixed columns. Type evidence feeds MAP-TYPE-GUARD: a fuzzy (MAP-003) match onto a numeric
canonical field is rejected when the column contains no numeric-like values at all.

## Canonical field types (dictionary level)

- `identifier` — verbatim string + `value_normalized` (NFKC/casefold) used in duplicate context keys.
- `string` — verbatim trimmed string.
- `numeric` — may resolve to `value`, to `low`/`high` (range), to `value` + `uncertainty` (±),
  or to null (missing / unparseable / unknown unit). A numeric field with a `dimension` is
  normalized to that dimension's target unit; with `plausible_range` it is range-checked
  (flagged, never clipped).

## Split / composite field conventions

- **Split columns** (`Yield_min (%)` + `Yield_max (%)`): MAP-004 maps each column to one
  endpoint of the canonical range; the composed cell keeps both endpoints and is checked for
  inversion. Nothing is averaged.
- **Composite cells** (`72-80 %`): RANGE-SPLIT decomposes one cell into low/high.
- **Component header conventions** recognized: `min/max/low/high/lower/upper` prefixes or
  suffixes (underscore or token form), and Chinese 最小/最大/下限/上限/最低/最高.

## Schema versioning and migration

- `field-dictionary.json` carries `dictionary_id` + `schema_version`; `units.json` carries its
  own `version`. Both versions are recorded in every audit and mapping report.
- **Adding aliases, missing tokens, stop words, units or whole fields is backwards
  compatible**: no code change, results can only improve.
- **Renaming or removing a canonical field, or changing a `context_key` flag, is a breaking
  change**: bump `schema_version` (e.g. 1.0.0 → 2.0.0) and write a migration note here
  describing how previously cleaned outputs map onto the new fields. Because every cleaned row
  keeps its `raw` record and every change carries a rule id, re-running old inputs under a new
  dictionary version reproduces the migration deterministically.
- Context-key changes alter duplicate grouping; treat them as scientific decisions and record
  the reason in the migration note.

### Migration log

| from | to | change | reason |
|---|---|---|---|
| — | 1.0.0 | initial dictionary (record_id, doi, title, locator, material, property, temperature, pressure, reaction_time, yield, selectivity, conversion, energy, notes) and unit table (temperature, pressure, time, energy, length, percent) | first release |
