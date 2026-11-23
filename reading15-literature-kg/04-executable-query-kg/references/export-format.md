# 导出格式与哈希清单（export-format）

`kg_export.py --graph <图谱> --out-dir <目录>` 一次导出全部格式。
所有产物**确定性**：节点/边按 id 排序、JSON 键排序、CSV 行序固定、不含时间戳与
主机信息；同一图谱在任何机器上重跑得到逐字节一致的文件。

## 文件

| 文件 | 格式 | 说明 |
|-|-|-|
| `graph.json` | JSON | 规范图谱：schema_version、graph_id、case_id、graph_hash、sources、nodes、edges、merge_decisions |
| `graph.jsonl` | JSONL | 每行一条：`kind=node` / `kind=edge` / `kind=merge_decision`，便于流式处理与 diff |
| `nodes.csv` | CSV | id, type, name, aliases, n_evidence, sources |
| `edges.csv` | CSV | id, src, relation, dst, conditions, n_evidence, sources |
| `graph.md` | Markdown | 人类可读邻接表：来源清单 → 每节点一节（类型/别名/证据/出边→/入边←，含条件与证据）→ 合并决策表 |
| `graph.svg` | SVG | 无依赖预览（见下） |
| `manifest.json` | JSON | 哈希清单（见下） |

## SVG 预览（无依赖）

- 手写 XML，不依赖任何图形库；UTF-8 中文标签；
- 布局：节点按 `type` 分列（固定类型顺序 Researcher/Material/Method/Task/Metric/
  Sample/Condition/Conclusion，其余类型字母序追加），列内按 id 排序均匀排布；
- 节点框：名称（超长截断加 …）+ 类型 + id；颜色按类型；
- 边：src→dst 直线 + 箭头，中点红色关系标签；标签带 `*` 表示该边有
  `conditions`（适用条件约束），提醒复核者注意数值/样品归属；
- 页脚含 graph_hash 前缀，便于把图与清单对应。

## manifest.json（哈希清单）

```json
{
  "graph": "<绝对路径>", "out_dir": "<绝对路径>",
  "graph_hash": "sha256(规范化 sources+nodes+edges+merge_decisions)",
  "counts": {"nodes": N, "edges": M, "sources": 2, "merge_decisions": K},
  "files": {"graph.json": {"sha256": "…", "bytes": …}, …}
}
```

复核方式：`sha256sum graph.json …` 与清单逐项比对；graph_hash 可用
`kg_loader.load_graph(...).graph_hash()` 复算。任何内容改动都会导致哈希变化，
因此"导出产物 ↔ 图谱内容"的对应关系是可机检的。
