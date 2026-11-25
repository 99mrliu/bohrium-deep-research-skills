# 模型抽取文件格式（extraction JSONL）与查询规格

模型唯一需要手写的工件是 `/app/work/extractions.jsonl`（以及有界修复时的
`/app/work/repair.jsonl`）：每行一个 JSON 对象，`op` 字段区分操作。其余一切
（校验、隔离、建图、查询、组装）都由脚本机械完成。

## 1. 操作（op）一览

### node — 实体节点
```json
{"op":"node","id":"n01","type":"material","label":"MAPbI3",
 "evidence":{"source_id":"SRC-P","paragraph_id":"p3","quote":"MAPbI3 films were ..."}}
```
- `type` 必须是本体中的 9 种实体类型之一。
- `id` 在本文件内唯一，建议 `n01, n02, ...`。
- `evidence.quote` 必须是 `source_id`+`paragraph_id` 所指段落原文的精确子串。

### edge — 类型化关系边
```json
{"op":"edge","id":"e01","relation":"reports","subject":"n10","object":"n04",
 "qualifiers":{"value":21.1,"unit":"%","condition":"1-sun initial measurement"},
 "evidence":{"source_id":"SRC-P","paragraph_id":"p7","quote":"reached a PCE of 21.1%"}}
```
- `relation` 必须是本体中的 9 种关系之一；domain/range 按 subject/object 节点类型校验。
- `qualifiers` 只能使用本体声明的键；必需限定词缺失 → `MISSING_QUALIFIER`；
  带数值 `value` 而缺 `metric`/`condition` → `NUMERIC_REQUIRES_METRIC_CONDITION`。
- 可选 `"polarity"` 字段若出现，必须与该关系在本体中的固定极性一致。

### merge — 跨篇/跨名合并（须理由）
```json
{"op":"merge","keep":"n01","drop":"n21","reason":"alias pair: MAPbI3 = methylammonium lead iodide, both the absorber material",
 "evidence":{"source_id":"SRC-S","paragraph_id":"p2","quote":"methylammonium lead iodide (MAPbI3)"}}
```
- `keep` 保留、`drop` 并入；两者必须同实体类型。
- `sample` 与 `claim` 类型不允许 merge（校验拒绝）。

### nonmerge — 显式不合并（同名不同物）
```json
{"op":"nonmerge","a":"n05","b":"n23","reason":"TiO2 in primary is the mesoporous ETL of device A; in secondary it is a compact layer of a different device",
 "evidence":{"source_id":"SRC-P","paragraph_id":"p5","quote":"mesoporous TiO2"}}
```

### unreported — 未报告项
```json
{"op":"unreported","item":"hysteresis index","reason":"secondary paper does not report hysteresis",
 "evidence":{"source_id":"SRC-S","paragraph_id":"p8","quote":"..."}}
```
（若全文未提及、无 quote 可引，允许 `evidence.quote` 为空字符串并在 reason 中说明"全文未出现"；
校验器此时只校验地址存在性。）

### note — 自由备注（不确定项、文献内部冲突 preservation 等）
```json
{"op":"note","text":"source-internal conflict preserved: primary reports both 21.1% (initial) and 20.4% (stabilized)"}
```

## 2. 查询规格（case.json 的 query_specs，三种类型）

```json
{"query_id":"q1","type":"neighborhood","entity":"MAPbI3","depth":1,
 "relation_filter":["uses","aliases","measures"]}
{"query_id":"q2","type":"edges_of_relation","relation":"reports",
 "qualifier_filter":{"metric":"power conversion efficiency (PCE)"}}
{"query_id":"q3","type":"contradiction_check","claim_a":"PCE 21.1% at 1-sun initial",
 "claim_b":"PCE 18.7% retained after 500 h damp-heat"}
```

- `neighborhood`：按 label 模糊匹配实体（casefold 前缀/子串），返回 depth 层内子图；
  `relation_filter` 可限定只沿哪些关系走。
- `edges_of_relation`：返回某关系类型的全部边，支持 `qualifier_filter`（限定词等值过滤）。
- `contradiction_check`：定位两个 claim，检查之间是否存在 `contradicts`/`compares` 路径，
  并列出两边的 condition 差异与"未决"关系。

每个查询结果都含：`status`（ok / no_match / unknown_entity）、`subgraph`（nodes+edges）、
`evidence`（每条边的引用与 quote）、`undetermined`（显式列出的未知/未决关系）。
