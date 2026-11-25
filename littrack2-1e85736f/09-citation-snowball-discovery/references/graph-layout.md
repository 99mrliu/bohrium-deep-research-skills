# 图谱文件布局约定与 locator 规则

`scripts/graph_load.py` 兼容两类布局，边语义统一为 **`source -> target` 表示 "source 引用 target"**（backward 方向）。forward 扩展即沿该约定反向取边。

## 布局 1：nodes/edges

```json
{
  "nodes": [
    {"id": "seed-a", "doi": "10.xxxx/...", "title": "...", "abstract": "...", "year": 2025}
  ],
  "edges": [
    {"id": "e0", "source": "seed-a", "target": "ref-1"}
  ]
}
```

- `nodes` 也接受对象形式 `{"<id>": {...}}`；节点 id 依次尝试 `id`、`node_id`、`doi` 字段。
- 边支持 `source/target` 或 `from/to`；可选 `id`（缺省自动生成 `e<i>`）。
- 边若带 `"relation": "cited_by"`，表示该记录声明的是"source 被 target 引用"，加载时翻转为 `target -> source`，其余 relation 值一律按 source 引用 target 处理。
- locator：节点 `/nodes/<i>`（数组）或 `/nodes/<id>`（对象），边 `/edges/<i>`。

## 布局 2：adjacency

```json
{
  "adjacency": {"seed-a": ["ref-1", "ref-2"]},
  "cited_by":  {"seed-a": ["paper-x"]},
  "node_records": {"ref-1": {"title": "...", "year": 2024}}
}
```

- `adjacency[A] = [B, ...]` 表示 A 引用 B（backward）。
- 可选 `cited_by[A] = [X, ...]` 表示 X 引用 A，加载时生成 `X -> A` 边（forward 来源）。
- 可选 `node_records` 提供节点元数据；仅出现在边里的节点会被补空记录，其 `node_locator` 为 `null`，结果中如实体现（材料未提供该节点的元数据）。
- locator：`/adjacency/<src>`、`/cited_by/<tgt>`、`/node_records/<id>`。

## locator 通用规则

- locator 一律是**材料文件内的 JSON 指针片段**（以 `/` 开头），配合 `channels.*.source` 给出的文件相对路径即可精确定位。
- 结果中引用 locator 时，应能由"文件路径 + locator"回指到产生该事实的原始记录（节点、边、快照条目）。
- 快照（Crossref 风格）条目的 locator 形如 `/message/items/<i>`。

## 缺口处理

- 边指向 `nodes`/`node_records` 未收录的 id → **dangling reference**，单独列入 `expansion.dangling_references`（含边 locator 与缺失 id），不进入候选集。
- 种子在图谱中既无节点也无任何边 → 列入 `expansion.seeds_missing`，并按异常处理 C 降级 partial。
