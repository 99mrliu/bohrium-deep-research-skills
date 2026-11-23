# Audit — schema-cartographer v1.0.0

Synthetic/local runs of this audit are examples only, never official case answers.

## Run identity
- case_id: `synthetic-demo-0001`
- status: **success**
- input_sha256: `9c03c0b60fbc1f41b0b626f61dca18404992f60f8b583d1cd64d62305164be07`
- case file: `case.json`; task file: `task.md`
- dictionary: `lit-extract-core` schema_version `1.0.0`
- unit table: `lit-extract-units` version `1.0.0`
- wall-clock timestamps are intentionally omitted so identical inputs produce byte-identical outputs.

## Sources
- `case.json/records` (json_records): 6 rows
- `case.json/material_csv` (csv): 6 rows
- `case.json:material-batch-c.csv` (csv): 4 rows

## Schema profile and mapping
- profiled columns: 28; mapped: 25; unmapped: 3

| column | canonical field | component | confidence | rule | semantic type |
|---|---|---|---|---|---|
| `extraction.id` (case.json/records) | `record_id` |  | 0.99 | MAP-001 exact normalized alias match | identifier |
| `extraction.doi` (case.json/records) | `doi` |  | 0.99 | MAP-001 exact normalized alias match | identifier |
| `material.name` (case.json/records) | `material` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `property` (case.json/records) | `property` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `conditions.temperature` (case.json/records) | `temperature` |  | 0.78 | MAP-003 alias plus stop-word tokens | numeric |
| `conditions.pressure` (case.json/records) | `pressure` |  | 0.78 | MAP-003 alias plus stop-word tokens | numeric |
| `yield` (case.json/records) | `yield` |  | 0.99 | MAP-001 exact normalized alias match | numeric |
| `notes` (case.json/records) | `notes` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `Ea (eVee)` (case.json/records) | `energy` |  | 0.99 | MAP-001 exact normalized alias match | numeric |
| `Material Name` (case.json/material_csv) | `material` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `DOI` (case.json/material_csv) | `doi` |  | 0.99 | MAP-001 exact normalized alias match | identifier |
| `Property` (case.json/material_csv) | `property` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `T / K` (case.json/material_csv) | `temperature` |  | 0.99 | MAP-001 exact normalized alias match + MAP-005 unit-hint disambiguation | numeric |
| `P_MPa` (case.json/material_csv) | `pressure` |  | 0.92 | MAP-002 alias plus '_UNIT' suffix convention | numeric |
| `Yield_min (%)` (case.json/material_csv) | `yield` | low | 0.99 | MAP-004 component (min/low/max/high) convention on aliased header | numeric |
| `Yield_max (%)` (case.json/material_csv) | `yield` | high | 0.99 | MAP-004 component (min/low/max/high) convention on aliased header | numeric |
| `Selectivity` (case.json/material_csv) | `selectivity` |  | 0.99 | MAP-001 exact normalized alias match | numeric |
| `Notes` (case.json/material_csv) | `notes` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `catalyst name` (case.json:material-batch-c.csv) | `material` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `文献DOI` (case.json:material-batch-c.csv) | `doi` |  | 0.99 | MAP-001 exact normalized alias match | identifier |
| `指标` (case.json:material-batch-c.csv) | `property` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `温度(摄氏度)` (case.json:material-batch-c.csv) | `temperature` |  | 0.99 | MAP-001 exact normalized alias match | numeric |
| `压力` (case.json:material-batch-c.csv) | `pressure` |  | 0.99 | MAP-001 exact normalized alias match | numeric |
| `收率(%)` (case.json:material-batch-c.csv) | `yield` |  | 0.99 | MAP-001 exact normalized alias match | numeric |
| `备注` (case.json:material-batch-c.csv) | `notes` |  | 0.99 | MAP-001 exact normalized alias match | string |
| `Instrument Serial` (case.json/records) | *(unmapped: no_alias_candidate)* | | 0.00 | see unresolved-schema.json | identifier |
| `Mystery Column` (case.json/material_csv) | *(unmapped: no_alias_candidate)* | | 0.00 | see unresolved-schema.json | identifier |
| `weird_col` (case.json:material-batch-c.csv) | *(unmapped: no_alias_candidate)* | | 0.00 | see unresolved-schema.json | identifier |

## Units and value cleaning
- unit conversions applied: 16 (every entry records formula, factor, offset and 12-significant-digit rounding)
  - `K = degC * 1 + 273.15`
  - `MPa = bar * 0.1`
- range splits (low/high preserved, no midpoint invented): 2
- unknown units (no conversion, values left null, raw preserved): 1
  - `eVee` (dimension energy) on ['case.json/records::Ea (eVee)']

## Duplicate detection (conservative)
- groups flagged: 3; no row was merged or dropped.
- `DG-0001` scientific_conflict_requires_human_adjudication: rows ['R000001', 'R000002', 'R000003']
- `DG-0002` scientific_conflict_requires_human_adjudication: rows ['R000007', 'R000008', 'R000009']
- `DG-0003` scientific_conflict_requires_human_adjudication: rows ['R000013', 'R000014', 'R000015']
- context keys come from dictionary `context_key: true`; rows with <2 non-empty context parts are not compared.

## Missing values, anomalies and review
- missing cells preserved as null: 12
- anomalies: 4; review items: 6
- unresolved output-contract fields: 1 ['adjudication_workbook']

## Traceability and self-check
Every cleaned row keeps `raw` (original flattened record) and per-field `source_column`;
every changed value has a rule-coded entry in change-log.jsonl with old/new values and source locator.
Re-run with identical inputs and diff the output directory: all files must be byte-identical.

