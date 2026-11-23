# 复现与核对（reproduction）

目标：第三方（或复核 Agent）只凭本 Skill 与输入材料，就能重放全部结果并机检一致性。

## 完整重放

```bash
# 需要：/input/{case.json, material.json, primary-material.json,
#        secondary-material.json, corpus-manifest.json}（可选 *.xml）
#       /app/work/{graph.candidate.json, queries.json}（Agent 撰写的语义产物）
python3 scripts/run_all.py --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output
```

流水线阶段与早存策略：
1. 阶段0：立即写出最早 `result.json`（status=partial），中途任何失败都留有可接管产物；
2. 阶段1：`kg_validate` 结构 + 证据核验 → `validation_report.json`；不过则 status=blocked 并逐条列因；
3. 阶段2：`kg_export` 导出 6 种文件 + `manifest.json`；
4. 阶段3：`run_queries` 实际执行查询 → `query_results.json` + `query_snapshot.json`；
5. 阶段4：`finalize` 汇总 `result.json`（动态镜像 output_contract 全部键；成功/部分完成/无法判断如实区分）。

每个阶段完成后都会刷新 `result.json`，因此崩溃现场本身就是部分交付物。

## 机检一致性（不重新执行也能核对）

```bash
# 1) 导出文件哈希 ↔ manifest.json
cd /app/output && shasum -a 256 graph.json graph.jsonl nodes.csv edges.csv graph.md graph.svg

# 2) 查询结果 ↔ 快照（graph 与 queries 未改动）
python3 scripts/run_queries.py --graph /app/work/graph.candidate.json \
    --queries /app/work/queries.json --out-dir /app/output --check   # 一致退出 0

# 3) 证据 ↔ 原文
python3 scripts/kg_validate.py --graph /app/work/graph.candidate.json \
    --materials /input/primary-material.json /input/secondary-material.json
```

## 确定性保证

- 所有哈希为 sha256 的内容哈希（排序键、去空白差异的规范化 JSON），**不含时间戳**；
- 节点/边/决策按 id 排序，邻接展开按 edge_id 排序，BFS 最短路径确定唯一；
- 同一 (graph, queries) 输入在任何 Python3 环境重跑，`result.json` 中除路径字段外逐字节一致。

## 改动留痕

改动查询或图谱后重跑：不带 `--force` 被拒绝（退出码 4）；带 `--force` 后快照记录
`rerun_after_mismatch=true` 与 `previous_snapshot_hash`，`result.json` 的 `changes`
数组按阶段记录每次执行的动作——不允许"悄悄换结果"。
