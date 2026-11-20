---
name: dir-aware-snowball-tracer
description: 以种子论文为起点做方向感知的多跳引文雪球追踪（后向参考文献＋前向施引文献），带分支剪枝、停止判据和逐边数据源证据。当任务要求从一篇种子论文出发沿引用关系扩展文献集、并保留每条引用边的来源与方向时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约，也适用于任何给出 DOI/arXiv/标题的种子追踪任务。
---

# 方向感知多跳引文雪球追踪（dir-aware-snowball-tracer）

## 用途与适用条件

从一篇种子论文出发，沿**后向参考文献**找到方法与数据出处，沿**前向施引文献**找到后续改进与批评；支持多层级扩展、分支剪枝和停止判断，避免只取一层。每条引用边都带可回指的数据源定位（文件＋JSON 路径/行号），每条保留/剪枝决策都有日志。

不适用：普通关键词检索、全文内容理解。本 Skill 只做引文关系追踪与证据记录。

## 输入

- `/input/case.json`：案例文件，含 `case_id`、种子论文标识（DOI/arXiv/标题，可能在 `seed_paper`、任务文本或材料引用中）、`output_contract`。
- `/input/task.md` 或 `task.md`：任务说明，其关键词用于相关性剪枝。
- 本地语料：组织方提供的 Crossref/EuropePMC/出版方响应、保留的引用图、增量导入状态等，可能位于 `/input`、`./environment`、`/app/work` 或当前目录。脚本自动发现 `.json/.jsonl/.csv/.tsv/.edgelist` 文件并解析异构格式。

## 调用方式（按顺序执行）

```bash
# 1. 追踪（默认参数适合 900 秒预算；语料大时把 --max-nodes 降到 150）
python3 scripts/snowball_trace.py --case /input/case.json --out /app/output --workdir /app/work

# 2. 自查（必须运行；失败项要写入 result.json 的 uncertainty）
python3 scripts/verify_trace.py /app/output /app/work
```

可选参数：`--max-depth`（默认 3 层）、`--max-nodes`（默认 250）、`--max-branch`（单节点最大扩展分支，默认 40）、`--year-min`、`--allow-net`（默认关闭；开启后仅做一次 best-effort Crossref 核对并记录 URL，失败不影响结果）。语料根目录可用 `--roots` 追加。

## 输出（/app/output）

- `result.json`：`case_id`、`status`（ok/partial/failed）、`seed`（含解析尝试记录）、`nodes`（含层级、方向、定位）、`edges`（含方向、语义说明、数据源定位）、`layers` 统计、`pruning_log`、`stop_log`、`sources`、`evidence_records`、`uncertainty`，并镜像 `output_contract` 的全部字段。
- `trace_graph.json`：节点与边的精简图，便于复核。
- `evidence_table.md`：人读证据表，逐节点、逐边列出数据源定位。
- 运行日志在 `/app/work/run_log.json`，自查报告在 `/app/work/verify_report.json`。

## 关键方法（详见 rules/traversal_policy.md）

1. **方向恢复**：数据源只给参考文献列表时，将本地语料中所有"参考文献指针"反向索引，凡引用了种子或已扩展节点的本地记录都计为前向边；显式 citations 列表与反向边合并去重。方向语义在每条边上标注（reference=citing→cited，citation=cited→citing）。
2. **多跳扩展**：BFS 逐层推进；同层内后向分支沿"文献的参考文献"继续，前向分支沿"施引文献"继续，避免方向混杂的指数爆炸。
3. **剪枝**：单节点分支数超过 `--max-branch` 时按被引提示＋任务关键词重叠保留高价值分支；过老文献（早于种子 `--year-span` 年）除非被引提示 ≥ `--classic-cited-by`（奠基性经典）否则剪除；所有剪枝写入 `pruning_log`。
4. **停止**：节点预算耗尽或某层零新增即停止，写入 `stop_log`；不为了凑数而放宽判据。
5. **存根诚实性**：本地语料中无法解析出完整元数据的引用目标保留为 `stub=true` 节点，只带原始指针字段与定位，**绝不**补造作者、年份或摘要。

## 异常处理

| 情况 | 处置 |
|-|-|
| 种子在本地语料中找不到 | `status=partial`，`seed=null`，`seed_resolution_attempts` 记录全部尝试；交付语料摘要，不伪造追踪结果 |
| 种子无前向引用记录（新预印本常见） | 正常交付后向结果；在 `uncertainty` 说明"本地来源无前向记录"，并用反向索引补查一次 |
| 引用目标无法解析 | 保留 stub 节点并计数，列入 `uncertainty` |
| 文件损坏/格式不识 | 跳过并记入 `sources` 的 parse notes；不中断运行 |
| 跨库字段冲突（同 DOI 不同标题等） | 以第一条完整记录为准合并，冲突字段保留在原记录 locator 中可追溯；在 `uncertainty` 说明 |
| `--allow-net` 网络失败 | 仅记日志，结果仍以本地证据为准 |

## 自查方法

运行 `verify_trace.py` 后：若 `ok=false`，把失败项逐条写入 `result.json.uncertainty`，能修复的（如缺 case_id）修复后重跑。交付前确认：每条边都有 `source.file`；`status` 与实际完成情况一致；没有任何节点的元数据来自推测。

## 最小调用示例

见 `examples/example_walkthrough.md`（合成玩具语料，仅说明接口，**非正式案例结果**）。
