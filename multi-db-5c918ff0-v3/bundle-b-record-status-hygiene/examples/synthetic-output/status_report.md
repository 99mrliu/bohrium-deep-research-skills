# 文献状态卫生报告（Record Status Hygiene Report）

- case_id: `synthetic-status-hyg-001`
- skill: `record-status-hygiene` v1.0.0
- 记录总数: 11 | severe: 5 | flagged: 1 | unverifiable: 1 | 显式版本对: 1 | 待审版本对: 0 | import 不一致: 1

> 本报告全部状态证据来自案例材料内部的显式字段/关系/引用图属性；未做任何外部撤回库查询。查不到状态 ≠ 干净：无状态面的记录一律标 `unverifiable`，不进入候选池。

## 严重状态记录（severe — 一律排除出候选池）

| record_id | doi | 原因码 | 证据定位符 | 处置 |
|---|---|---|---|---|
| crossref:10.99231/synth.002 | 10.99231/synth.002 | CROSSREF_IS_RETRACTION_OF | materials/crossref_response.json::$.message.items[1].relation[0] | exclude_as_retracted |
| crossref:10.99231/synth.002t | 10.99231/synth.002t | REFGRAPH_NODE_WITHDRAWN, REFGRAPH_RETRACTION_EDGE, TARGET_RETRACTED | materials/reference_graph.json::$.nodes[0]; materials/reference_graph.json::$.edges[0]; materials/crossref_response.json::$.message.items[1].relation[0] | exclude_as_retracted |
| europepmc:10.99231/synth.epmcret1 | 10.99231/synth.epmcret1 | EPMC_RETRACTION_OF_PUBLICATION | materials/europepmc_response.json::$.resultList.result[0].pubTypeList | exclude_as_retracted |
| publisher:10.99231/synth.pub2 | 10.99231/synth.pub2 | REFGRAPH_NODE_WITHDRAWN | materials/reference_graph.json::$.nodes[4] | exclude_as_retracted |
| publisher:10.99231/synth.pub3 | 10.99231/synth.pub3 | IMPORT_STATE_WITHDRAWN | materials/import_state.json::$.records[3] | exclude_as_retracted |

## 标记记录（flagged — 需模型裁定）

| record_id | doi | 原因码 | 证据定位符 | 处置 |
|---|---|---|---|---|
| publisher:10.99231/synth.pub1 | 10.99231/synth.pub1 | PUBLISHER_STATUS_NOTICE | materials/publisher_records.json::$[0].status | keep_with_notice |

## 状态不可核验记录（unverifiable — 不视为干净，不入候选池）

| record_id |
|---|
| crossref:10.99231/synth.001 |

## 版本归并（preprint ↔ VoR）

| pair_id | preprint | VoR | 依据 | 证据 |
|---|---|---|---|---|
| pair-01 | crossref:10.99231/synth.004 | crossref:10.99231/synth.005 | explicit | materials/crossref_response.json::$.message.items[3].relation[0] |

## import_state 对账

- **import_inconsistent**: `crossref` / `10.99231/synth.404` — 声称已导入但在所有在场响应中均不存在（隔离该声明；证据 `materials/import_state.json::$.records[1]`）
- **withdrawn_excluded**: `publisher` / `10.99231/synth.pub3` — import_state 标记 'withdrawn'，已从候选池排除（证据 `materials/import_state.json::$.records[3]`）
- not_yet_imported（信息性）: `crossref:10.99231/synth.002`, `crossref:10.99231/synth.002t`, `crossref:10.99231/synth.004`, `crossref:10.99231/synth.005`, `europepmc:10.99231/synth.epmcret1`, `europepmc:10.99231/synth.ppr1`, `publisher:10.99231/synth.pub1`, `publisher:10.99231/synth.pub2`

## 候选池结论

- 入选候选（状态核验通过或保留并附注意）: **4 项研究**
- 排除（severe / 模型排除）: 5 条记录
- 状态不可核验（未入选，需人工补证）: 1 条记录
