---
name: executable-query-kg
description: 可执行查询的文献知识图谱引擎——Agent 依据 /input 中两篇论文（primary/secondary-material，含 corpus-manifest/material 索引与可选 JATS XML）撰写带逐条证据（source_id + JATS paragraph_id + 原文短引）的候选图谱与查询集，纯标准库确定性脚本负责结构校验、证据原文精确子串核验、导出（JSON/JSONL/CSV/Markdown 邻接表/无依赖 SVG/哈希清单）并真正执行 JSON 查询 DSL（node_lookup、带关系/方向/类型过滤的 neighborhood、shortest_path、cross_source 跨源证据、merge_decisions 合并且不合并依据），每个答案都由引擎在图上算出而非叙述，未知算子诚实拒绝、无结果诚实为空，查询快照哈希支持复核与重跑失配检测，result.json 动态镜像 output_contract 全部键。Use when a task provides fixed paper materials (JATS paragraph ids, no PDF pages) and requires a validated evidence-bound knowledge graph with reproducible executable queries, honest empty results, cross-paper merge/non-merge rationale, deterministic exports and previews (文献知识图谱, 证据绑定, 图谱查询, 实体对齐, 跨源证据, 可复核导出, 空结果诚实).
---

# 可执行查询文献知识图谱（executable-query-kg）

## 何时使用

案例输入是组织方固定的**两篇论文材料**（`/input`：`case.json`、`task.md`、`corpus-manifest.json`、`material.json`、`primary-material.json`、`secondary-material.json`、可选 `secondary-publisher.xml`），要求构建**带证据、可查询、可复核**的文献知识图谱。核心立场：**每个答案都由确定性引擎在图上实际算出**，不允许"叙述式回答"；查询先行——先写下验收查询，再让图谱内容满足它们。

分工（不可互换）：

- **Agent（语义层，你）**：通读两篇原文，撰写 `graph.candidate.json`（实体/关系/证据/合并与不合并决策）与 `queries.json`（≥3 条真实查询，建议含 1 条真实无结果查询）。格式见 `references/candidate-graph-spec.md` 与 `references/query-dsl.md`。
- **脚本（确定性层）**：校验、导出、执行查询、汇总。脚本不替你写答案；校验不过就阻塞并说明原因。

## 运行方式

```bash
# 0) Agent 先写两个文件（工作目录 /app/work）：
#    /app/work/graph.candidate.json   —— 候选图谱（格式见 references/candidate-graph-spec.md）
#    /app/work/queries.json           —— 查询集（≥3 条，格式见 references/query-dsl.md）

# 1) 一条命令跑完整流水线：校验 → 导出 → 执行查询 → 汇总 result.json
python3 /skills/weekly-skill/scripts/run_all.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output

# 2) 分步调试（可选）：
python3 /skills/weekly-skill/scripts/kg_validate.py \
    --graph /app/work/graph.candidate.json \
    --materials /input/primary-material.json /input/secondary-material.json \
    --report /app/output/validation_report.json
python3 /skills/weekly-skill/scripts/kg_export.py \
    --graph /app/work/graph.candidate.json --out-dir /app/output
python3 /skills/weekly-skill/scripts/run_queries.py \
    --graph /app/work/graph.candidate.json --queries /app/work/queries.json \
    --out-dir /app/output

# 3) 复核者验证产物未被改动（哈希一致性核对，不重新执行）：
python3 /skills/weekly-skill/scripts/run_queries.py \
    --graph /app/work/graph.candidate.json --queries /app/work/queries.json \
    --out-dir /app/output --check
```

**预算意识**：全部脚本 0 次模型请求、秒级完成；模型只用于第 0 步的语义撰写（建议 1–3 次请求：读材料 → 写候选图谱 → 写查询）。先跑通流水线拿到 partial 产物，再迭代丰富图谱。

## 关键规则（对应题目硬约束）

1. **证据三要素**：每个节点/边的每条证据必须含 `source_id`（须在 `sources` 声明）、`paragraph_id`（组织方 JATS 段落 ID）、`quote`（该段落原文的**精确短引**，≤200 字符）。校验器会把 quote 与材料段落原文做精确子串比对，并把段落实际所属文件与 source_id 声明的文件比对——把 secondary 的段落挂到 primary 上会被拒绝。**禁止 PDF 页码字段**（`page`/`页码` 等直接报错），本包无 PDF 页码。
2. **根元数据只属第一篇**：`case.json` 根部的 DOI/title/authors 只属于 primary（S1），不得套到 secondary。
3. **合并与不合并都要显式记录**：跨篇同一概念合并为 `canonical_node` 并写 `rationale`；同名/相似但不同对象（不同样品、条件、指标、数值）必须 `no_merge` 并写明依据。**相同方法/材料术语不代表相同物理样品、模型实例、数据集或实验条件**；两篇的数值结果禁止合成一个结论。e4/e7 式的数值边必须在 `conditions` 中注明适用范围。
4. **查询诚实性**：无结果就是 `status=empty` 并给出原因（未找到节点/路径不可达/仅单源）；未知算子是 `status=error, unknown_operator`，**拒绝执行而非静默为空**。
5. **快照与重跑**：`query_snapshot.json` 记录 graph_hash 与每条 query_hash（无时间戳，纯内容哈希）。改动查询或图谱后重跑必须 `--force`，快照如实记录 `rerun_after_mismatch` 与 `previous_snapshot_hash`；复核者用 `--check` 核对。

## 产物（/app/output）

| 文件 | 内容 |
|-|-|
| `result.json` | case_id、status/partial、**动态镜像 output_contract 全部键**、sources、uncertainty、changes、artifacts（含 sha256） |
| `graph.json` / `graph.jsonl` / `nodes.csv` / `edges.csv` | 规范图谱导出（节点按 id 排序，含证据） |
| `graph.md` | 人类可读邻接表（每节点：类型、别名、证据、出/入边及条件） |
| `graph.svg` | 无依赖 SVG 预览（类型分列、名称/类型/id 标签、带箭头边与关系标签，`*` 表示有条件约束） |
| `manifest.json` | 各导出文件 sha256 + graph_hash + 计数（确定性，可复算） |
| `validation_report.json` | 结构 + 证据核验逐条报告 |
| `query_results.json` / `query_snapshot.json` | 每条查询的 status/结果/explain/哈希 + 快照 |

## 依赖与异常处理

- 仅 Python 3 标准库；无网络；UTF-8。
- 候选图谱缺失 → `status=blocked` 并说明缺什么、去哪补；材料缺失 → 只做结构校验并如实标注证据未核验（partial）。
- 校验不过 → 阻塞，`validation_report.json` 逐条列出问题（哪条证据、哪个段落、quote 为什么不匹配），修完重跑即可。
- 查询文件缺失 → 校验与导出照常完成，result.json 标 partial 并在 uncertainty 说明。
- 重复运行：产物确定性，内容不变则哈希不变；改动后未 `--force` 重跑会被拒绝（退出码 4）。

## 不适用边界

- 不做自动实体抽取（语义抽取是 Agent 的职责，脚本负责校验与查询）；不做问题拆解与文献检索。
- 查询是精确匹配（名称/别名大小写不敏感、关系精确匹配），不含语义向量检索；需要模糊匹配时在 uncertainty 中说明。
- SVG 为静态分列布局，适合 ≤数十节点规模的复核预览，不是交互式可视化。

## 最小调用示例（SYNTHETIC 合成示例，非正式案例结果）

`examples/minimal/` 内含两篇**合成**论文材料、候选图谱（12 节点 / 12 边 / 2 合并 + 3 不合并）与 7 条查询（含 1 条真实无结果 Q5、1 条单源跨源为空 Q7），`examples/minimal/output/` 为实际跑出的全部产物（带 SYNTHETIC 标签）：

```bash
python3 scripts/run_all.py \
    --case examples/minimal/materials/case.json \
    --input-dir examples/minimal/materials \
    --work /tmp/kg-work --out examples/minimal/output \
    --graph examples/minimal/graph.candidate.json \
    --queries examples/minimal/queries.json --label SYNTHETIC
# → 已执行 7 条查询：ok=5 empty=2 error=0；status=success
python3 tests/run_tests.py   # 23 项验收+负向测试
```

## 参考资料

- `references/candidate-graph-spec.md` — 候选图谱撰写规范（Agent 必读）
- `references/query-dsl.md` — 查询 DSL 全部算子、参数与 EXPLAIN 语义
- `references/export-format.md` — 导出格式与哈希清单
- `references/reproduction.md` — 复现与核对步骤（含快照哈希）
- `references/limitations.md` — 限制与诚实边界
