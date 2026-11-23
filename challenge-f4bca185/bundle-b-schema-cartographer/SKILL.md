---
name: schema-cartographer
description: 文献数据清洗与标准化 Skill,重心在异构字段映射与 schema 版本/语义类型协调。把一批真实文献抽取记录(JSON 嵌套记录、内嵌或外部 CSV 材料)清洗成可统计的规范化数据表:基于可编辑、带版本的字段字典做数据驱动的表头映射(每个映射给出置信度与证据,未映射列单独列出),推断语义类型(identifier/string/numeric/range/missing),在输入约定支持时拆分 min/max 复合列,做可辩护的单位归一(保留原值、写出公式与精度、未知单位绝不猜测),保守标记重复(上下文键防止错并,科学冲突绝不自动合并),并输出缺失/异常/复核清单、带规则编号的行级变更记录和完整审计。适用场景:不同文献或抽取工具给出的列名不一致、需要可追溯清洗的科研数据整理。不适用:凭换算替代科学冲突裁决、为缺失值编造数据。
---

# schema-cartographer

Heterogeneous literature-extraction cleaning with **field mapping + schema/semantic-type
coordination** as the center of gravity. Python 3.10+ standard library only; everything is
deterministic (byte-identical outputs for identical inputs); no wall-clock timestamps are emitted.

## When to use

- A batch of literature-extraction records arrives as nested JSON and/or CSV material whose
  column names differ across sources/extractors (`T / K`, `P_MPa`, `Yield_min (%)`, `温度(摄氏度)` …).
- You need one canonical, versioned schema — not memorized per-paper conventions — and a full
  audit trail: every changed value traceable to input row, rule id and source locator.
- You must NOT invent missing values, must NOT silently merge scientific conflicts, and unknown
  units/columns must be surfaced, not guessed.

## Inputs

- `--case` (default `/input/case.json`): case JSON. Records are harvested recursively:
  any list of objects becomes rows (nested objects flatten to dotted paths like
  `conditions.temperature`), any string that parses as a headered CSV table becomes rows, and any
  string ending in `.csv` that resolves to a file next to the case file is loaded. An optional
  `output_contract` object/list declares top-level result fields and their expected types
  (`dict`/`list`/`string`).
- `--task` (default `/input/task.md`): task text, hashed for provenance only.
- `--work` (default `/app/work`): scratch directory.
- `--out` (default `/app/output`): output directory.
- `--dictionary` / `--units`: override the editable reference resources
  (defaults: `references/field-dictionary.json`, `references/units.json`).

## Workflow

1. **Write honest partial first.** `result.json` (status `partial`) is written before any real
   work and upgraded at each stage, so a crash never leaves nothing behind.
2. **Ingest.** JSON nested records + embedded/external CSV → raw rows with source id and locator.
3. **Profile.** Per (source, header) column: missing/distinct counts, samples, semantic type
   (identifier / string / numeric / range / missing) with rule-coded evidence
   (see `references/types-and-migration.md`).
4. **Map.** Data-driven header mapping against the versioned field dictionary: exact alias
   (MAP-001, 0.99), `_UNIT` suffix convention (MAP-002, 0.92), stop-word fuzzy (MAP-003, 0.78),
   min/max component convention (MAP-004), unit-hint disambiguation (MAP-005), MAP-TYPE-GUARD
   (fuzzy numeric matches need value-level support), ambiguity → left unmapped + review
   (MAP-AMBIG). Every mapping carries confidence + evidence; unmapped columns go to
   `unresolved-schema.json` with profiles and samples.
5. **Clean.** Semantic values: ranges split into low/high (never averaged), `±` kept as
   uncertainty, missing tokens → null (MISS-001), units normalized via the unit table
   (UNIT-CONV with formula/factor/offset, 12 significant digits), unknown units → null +
   anomaly (UNIT-UNKNOWN), no default unit is ever assumed (unit=null + uncertainty note),
   plausible-range and inverted-range checks flag anomalies without clipping.
6. **Flag duplicates conservatively.** Context key = dictionary `context_key` fields
   (doi, material, property, temperature, …). Same context + same measured values →
   `exact_duplicate_candidate` (nothing dropped); same context + different measured values →
   `context_value_conflict` + high-severity review — never merged, literal unit arithmetic never
   replaces scientific adjudication. Rows with <2 non-empty context parts are not compared.
7. **Emit outputs + audit**, then fill the `output_contract`: known fields get real values,
   unknown fields become `null` and are listed in `unresolved_contract_fields` (never fabricated).

## Outputs (all under `--out`)

| file | content |
|---|---|
| `cleaned.csv` / `cleaned.json` | one row per input record: canonical values (+`__low/__high/__unc/__unit/__raw/__src` per field), duplicate status, flags, `unmapped_json`, full `raw` record preserved |
| `mapping-report.json` | every column mapping with confidence, rule, matched alias, unit hint and profile evidence; unmapped columns with reasons and samples |
| `unresolved-schema.json` | unmapped columns, unknown units, unresolved contract fields, dictionary version |
| `review-queue.json` | `missing` list, `anomalies` list, `reviews` (severity, kind, rule, evidence) |
| `change-log.jsonl` | one rule-coded entry per column mapping and per changed/kept-null/flagged value (old → new, source column, row id) |
| `audit.md` | run identity (input SHA-256), sources, mapping table, unit formulas, duplicate groups, traceability and self-check notes |
| `result.json` | `case_id`, `status`, `summary`, `sources`, `uncertainty`, `change_records`, `artifacts`, `duplicate_groups`, `review_required`, **all** `output_contract` top-level fields, `unresolved_contract_fields` |

## Exit codes and failure handling

- `0` success (review items may still exist — see `review_required`); `2` invalid input
  (missing/unparseable case file, zero harvestable records) — honest `input_error` result +
  audit are still written; `1` unexpected error — honest `partial` result with traceback.
- Unit unrecognized / conflicting header-vs-value units: no conversion, raw preserved,
  anomaly + review. Header matches several canonical fields: left unmapped, review. Empty table,
  encoding junk (UTF-8 BOM tolerated), sparse per-row columns: handled and logged.

## Configuration (how to adapt to a new batch)

- Edit `references/field-dictionary.json`: add canonical fields, aliases (any language),
  `context_key` flags, `plausible_range`, `missing_tokens`, `stop_header_tokens`; bump
  `schema_version` and record the change in `references/types-and-migration.md`.
- Edit `references/units.json`: add dimensions/units/aliases with `factor`/`offset`/`formula`.
  Anything not listed is treated as unknown and surfaced — by design.
- Rule catalogue and conflict-resolution order: `references/mapping-rules.md`.
- No code change is needed for new aliases, units or fields.

## Self-check

```bash
python3 scripts/selfcheck.py   # example run x2 + determinism + invalid-input tests, all must PASS
# manual variant: re-run into a fresh --out dir and diff; the 8 generated artifacts
# (cleaned.csv/json, mapping-report.json, unresolved-schema.json, review-queue.json,
# change-log.jsonl, audit.md, result.json) must be byte-identical.
```

Also: pick any changed value in `cleaned.csv`, find its `change_id` in `change-log.jsonl`, and
confirm it names the source column, source locator and rule; confirm every `null` corresponds to
a missing token or an unresolved unit and never to an invented number.

## Limits

- Header mapping is dictionary-driven, not learned; brand-new conventions need new aliases.
- Duplicate detection compares normalized values; it cannot adjudicate which conflicting value
  is scientifically right — that is what the review queue is for.
- Nested JSON lists of scalars are kept as JSON strings; only lists of objects become rows.
- Percent-like fields without an explicit unit are kept verbatim with `unit=null` (no assumption).
