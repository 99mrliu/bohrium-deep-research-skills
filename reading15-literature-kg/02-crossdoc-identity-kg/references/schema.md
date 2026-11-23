# 数据结构说明（Schema）

所有文件均为 UTF-8 JSON（或 JSONL/DOT/SVG/TXT 文本）。

## 1. mentions.json（Agent 写入 /app/work）

```json
{
  "meta": {"generic_terms": ["xrd", "sintering"]},
  "mentions": [{
    "mention_id": "M-A1",          // 必填，全局唯一
    "source_id": "SYN-A",          // 必填，独立论文标识（与 corpus-manifest 一致）
    "paragraph_id": "p-0001",      // 必填，组织方 JATS 段落 ID（非 PDF 页码）
    "surface": "LLZO",             // 必填，原文表面形
    "entity_type": "material",     // material/method/model/dataset/metric/task/conclusion/…
    "aliases": ["Li7La3Zr2O12"],   // 可选，已知别名（含缩写、全称、大小写变体）
    "quote": "逐字短引",            // 必填，该段落原文的连续子串
    "properties": {"chemical_formula": "Li7La3Zr2O12", "conditions": "…"},
    "numbers": [{"name": "R2", "value": 0.81, "unit": "1"}]
  }]
}
```

`properties` 中的定义性属性键见 `identity-policy.md` 第 1 节；
`source_id`/DOI 不得放入 `properties`。

## 2. relations.json（Agent 写入 /app/work，可选）

```json
{"relations": [{
  "edge_id": "R-A1",
  "subject": "M-A1",               // mention_id
  "predicate": "has_measurement",  // uses/compares/outperforms/supports/contradicts/
                                   // trained_on/characterized_by/applied_to/…
  "object": "M-A6",                // 与 object_literal 二选一
  "object_literal": {"label": "ionic conductivity", "node_kind": "metric"},
  "attributes": {"value": 3.2e-4, "unit": "S/cm", "conditions": "25 C"},
  "evidence": {"source_id": "SYN-A", "paragraph_id": "p-0001", "quote": "逐字短引"}
}]}
```

边证据不得携带 page 字段；引用被剔除提及的边一并剔除并记录。

## 3. identity-decisions.json（输出）

```json
[{
  "decision_id": "D-0001",
  "candidate_keys": ["llzo", "lithium lanthanum zirconium oxide"],
  "pair": ["M-A1", "M-B1"],
  "sources": ["SYN-A", "SYN-B"],
  "decision": "MERGE",              // MERGE / KEEP_DISTINCT / UNDECIDED
  "merge_basis": [{"kind": "defining_match", "attribute": "chemical_formula", "…": "…"}],
  "blocking_evidence": [{"kind": "numeric_conflict", "attribute": "R2", "…": "…"}],
  "rationale": "人类可读理由"
}]
```

同一对跨篇提及无论共享多少候选键只裁决一次。

## 4. graph.json / graph.jsonl（输出）

- 节点：`id`（稳定，裁决后分配）、`kind`（entity/aux）、`entity_type`、`name`、
  `aliases`、`merged_from`、`decision_refs`、`identity_status`
  （MERGED / SINGLETON / SOURCE_SCOPED）、`sources`（每项含
  `mention_id` / `source_id` / `paragraph_id` / `quote`）。
- 边：`id`、`subject`、`predicate`、`object`、`attributes`、
  `evidence`（`source_id` / `paragraph_id` / `quote`）。
- graph.jsonl：每行 `{"type":"node"|"edge", …}`；graph.dot 为 Graphviz 文本；
  graph.svg 与 preview.txt 为无依赖预览。

## 5. queries.json（输入规格与输出结果）

规格：`{"type":"neighbors","node_name":"LLZO"}` /
`{"type":"filter","entity_type":"material"}` /
`{"type":"path","start_name":"…","end_name":"…"}`。
结果：`status`（ok / no_result / no_path / error）+ `result` + `evidence`
（边/节点的逐字引文回链）。失败与无结果如实标注。

## 6. result.json（输出）

键集合动态镜像 `case.json.output_contract`（字典取其键、列表取其项），
并固定包含：`case_id`、`status`（success / partial）、`graph`、
`identity_decisions`、`conflicts`、`queries`、`uncertainties`、
`change_records`（逐步骤时间戳记录）。无自然映射的合同键保留 null 并在
`uncertainties` 中说明。
