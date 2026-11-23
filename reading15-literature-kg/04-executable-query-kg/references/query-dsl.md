# 查询 DSL（query-dsl）

查询集文件 `queries.json`：`{"queries": [ {"id", "op", "params": {...}}, ... ]}`。
由 `run_queries.py` 批量执行；单条语义见 `kg_engine.run_query`。每条结果带
`status`（`ok` / `empty` / `error`）、`explain`（匹配规则说明，EXPLAIN）、
`query_hash` 与 `result_hash`（内容哈希，确定性，无时间戳）。

## 通用约定

- **节点解析**：`node`/`from`/`to` 参数先按节点 id 精确命中，否则按 `name`/`aliases`
  去首尾空白、小写化后精确匹配；查无此节点 → `status=empty` 并注明"不存在"。
- **关系匹配（EXPLAIN 规则）**：`relation` 为字符串或字符串列表；边的 `relation`
  经去空白、小写化后与列表做**精确匹配**（列表内 OR）；不传则匹配全部关系。
  结果的 `explain.relation_rule` 会复述该规则，保证可人工复算。
- **方向**：`out`（只看 src=本节点的出边）/ `in`（只看入边）/ `any`。
- **诚实性**：未知 `op` → `status=error, error=unknown_operator`，**拒绝执行**；
  无结果 → `empty` + `reason`；绝不把"查不到"包装成"没有这回事"，也绝不补造。

## 算子

### node_lookup — 按名称/别名查节点

```json
{"id": "Q1", "op": "node_lookup", "params": {"name": "spiro-OMeTAD"}}
```

返回 `matches`（节点含别名与全部证据）。未命中 → `empty`（真实无结果示范）。

### neighborhood — 邻域查询（关系/方向/类型过滤）

```json
{"id": "Q2", "op": "neighborhood",
 "params": {"node": "n:tio2", "depth": 1, "direction": "any",
            "relation": ["制备", "促进"], "types": ["Method", "Metric"]}}
```

- `depth`：1–8（默认 1），BFS 逐层扩展；
- `types`：对端节点类型白名单（字符串或列表）；
- 返回 `matches.nodes`（含证据）与 `matches.edges`（含条件与证据）；
- 过滤后无边 → `empty` 并说明"给定过滤条件下没有匹配邻边"。

### shortest_path — 最短路径（含类型化两跳）

```json
{"id": "Q3", "op": "shortest_path",
 "params": {"from": "n:spin-coating", "to": "n:stability",
            "direction": "any", "relation": null, "max_depth": 6}}
```

- BFS（按 edge_id 排序展开，确定性最短）；`max_depth` 默认 8；
- 返回 `path.nodes` / `path.edges`（含证据）与 `path.length`；
- 不连通或超出深度 → `empty`，reason 明确区分"节点缺失"与"不存在路径"。

### cross_source — 跨源证据核验

```json
{"id": "Q4", "op": "cross_source", "params": {"node": "n:tio2"}}
```

汇总节点自身证据与其所有关联边证据中的 `source_id`：≥2 个不同来源 → `ok`
并按来源分组返回证据；仅单源 → `empty`（诚实报告"不构成跨源证据"）。
注意：只存在同篇多种文件格式不算跨篇证据——来源以 `sources` 声明的论文为单位。

### merge_decisions — 合并/不合并决策查询

```json
{"id": "Q6", "op": "merge_decisions", "params": {"decision": "all"}}
```

`decision` ∈ `all / merge / no_merge`；返回决策列表（left/right/canonical_node/
rationale/evidence）。这是"合并依据与不得合并冲突"的机读出口。

## 快照与重跑检测

`run_queries.py` 写出 `query_snapshot.json`（graph_hash + 每条 query_hash +
results_hash + snapshot_hash）：

- `--check`：只核对不执行；一致退出 0，失配退出 3 并逐项说明（复核者用）；
- 失配后不带 `--force` 重跑 → 退出 4，拒绝悄悄覆盖；
- `--force` 重跑 → 快照记录 `rerun_after_mismatch`、`previous_snapshot_hash`、
  `mismatch_items`，全程留痕。
