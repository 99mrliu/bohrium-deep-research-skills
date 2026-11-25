# query_specs — 自动执行的查询类型

`case.json` 的 `query_specs`（列表）由 `kg_run.py query` **确定性自动执行**，
无需模型参与。每个查询返回：结果子图（节点+边，带完整证据）、证据列表、
显式 `undetermined`（图中无法判定的关系）。已知 `query_id` 原样保留。

节点引用可用 **node id** 或 **名称精确匹配**（大小写不敏感；merge 后按
keep id 解析）。

## 支持的 type

### neighborhood
```json
{"query_id":"q1","type":"neighborhood","node":"methylammonium lead iodide","hops":1}
```
以节点为中心的 `hops` 跳无向邻域（BFS，遍历顺序确定排序）。
节点不存在 → `status=not_found`，记入 undetermined。

### by-relation
```json
{"query_id":"q2","type":"by-relation","relation":"contradicts"}
```
返回该关系类型的全部边及其端点子图。零命中时 `status=ok` 但
`undetermined=["no edges of relation 'X' found in graph"]` —— 显式说明
该关系在语料中无直接证据。

### path
```json
{"query_id":"q3","type":"path","from":"n_a","to":"n_b"}
```
无向 BFS 最短路（确定性排序）。无路径 → `status=no_path`，关系记为
undetermined，绝不臆造连接。

### conflict-check
```json
{"query_id":"q4","type":"conflict-check","claims":["n_cl_x","n_cl_y"]}
```
检查两条 claim 之间是否存在 `contradicts`/`conflicts-with` 边：
- 存在 → `status=conflict_preserved`，附两 claim 的 `conditions`
  （来自 qualifiers）与 `resolution="preserved"`；
- 不存在 → `status=no_conflict_edge`，兼容性记为 undetermined。

## 契约

- 至少执行 3 条真实查询（优先 `case.json` 的 `query_specs`）；少于 3 条
  时如实报告，`run_report.json` 的 budget_checklist 会标 warn。
- 未知 `type` → `status=unsupported`，不中断其余查询。
