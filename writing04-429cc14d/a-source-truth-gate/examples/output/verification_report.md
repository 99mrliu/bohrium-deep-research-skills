# 条目核验报告（verify_entries）

- 生成时间（UTC）：1970-01-01T00:00:00Z
- 条目文件：`examples/input/entries.jsonl`
- 快照文件：`examples/input/snapshot.json`（快照记录数：5）
- 核验依据：本报告仅以输入快照（snapshot）为核验依据，未进行任何联网核实；not_found_in_snapshot 表示快照覆盖不全，不等于条目系伪造；DOI 解析失败（传输层）与 Crossref 404 均不得作为删除条目的理由。

## 汇总

| 状态 | 数量 |
| --- | --- |
| invalid_input | 0 |
| metadata_conflict | 1 |
| not_checked | 0 |
| not_found_in_snapshot | 0 |
| suspected_fabricated | 1 |
| verified_identity | 4 |
| **总计** | 6 |

## 逐条目结果

### E1 — verified_identity

- 标题：基于虚构晶格材料 HNX-3 的热电转换效率研究
- 判定理由：doi_match_and_fields_consistent
- 证据：`{"matched_by": "doi", "snapshot_doi": "10.55001/fakej.2023.001"}`

### E2 — verified_identity

- 标题：城市绿地对夜间气温影响的模拟研究（合成示例）
- 判定理由：doi_match_and_fields_consistent
- 证据：`{"matched_by": "doi", "snapshot_doi": "10.55001/fakej.2021.014"}`

### E3 — verified_identity

- 标题：一种虚构酶 GMP-7 的催化动力学研究（合成示例）
- 判定理由：doi_match_and_fields_consistent
- 证据：`{"matched_by": "doi", "snapshot_doi": "10.55002/enz.2019.077"}`

### E4 — verified_identity

- 标题：合成语料标注一致性的统计方法研究
- 判定理由：title_match_and_fields_consistent
- 备注：by_title
- 证据：`{"matched_by": "title", "snapshot_doi": "10.55003/stat.2022.005"}`

### E5 — suspected_fabricated

- 标题：量子海绵吸水性能的虚构研究
- 判定理由：invalid_doi_syntax
- 证据：`{"doi": "10.1234 /bogus.2024.001"}`

### E6 — metadata_conflict

- 标题：合成数据增强在低资源机器翻译中的作用
- 判定理由：doi_resolves_but_fields_differ
- 冲突字段：
  - `year`：条目值 `2021` ≠ 快照值 `2020`
- 证据：`{"matched_by": "doi", "snapshot_doi": "10.55003/nlp.2020.011"}`

---
免责声明：本报告未联网核验；任何 suspected_fabricated / metadata_conflict 条目必须隔离登记，不得进入成品文献表。
