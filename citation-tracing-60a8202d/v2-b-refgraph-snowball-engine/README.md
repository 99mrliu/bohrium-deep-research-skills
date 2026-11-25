# refgraph-snowball-engine

方向感知的多跳雪球引文追踪引擎（Skill bundle），面向 challenge-60a8202d
「引文追踪与关联文献发现」。从种子论文出发，在**本地语料**上构建有向引用图，
沿后向参考文献与前向施引文献做分层 BFS 扩展，全程记录剪枝与停止依据，
交付可机器复核的追踪结果。

## 特性

- **引用图构建**：递归扫描候选根，解析 Crossref / EuropePMC / OpenAlex /
  通用节点 JSON / JSONL / CSV·TSV 边表 / edgelist / BibTeX；DOI+标题双键去重；
  每条记录与每条边携带 `sources: [{file, pointer}]` 定位。
- **前向边恢复**：只给参考文献列表的数据源，用全语料反向索引恢复前向边并标
  `direction_restored: true`。
- **方向感知 BFS**：同层内后向沿 references、前向沿 citations 扩展；
  分支上限、任务关键词相关性、年份下限三重剪枝，高被引奠基经典豁免；
  预算耗尽或整层零新增即停。剪枝/停止决策全部落盘（pruning_log / stop_log）。
- **诚实交付**：解析不出的引用目标保留为 stub（只有定位，不补造元数据）；
  result.json 逐字段镜像 case.json 的 output_contract，附 status 与 uncertainty。
- **机器自查**：verify_trace.py 校验 locator 门禁、方向一致性、悬空节点、
  契约镜像，输出 `ok=true/false` 与缺陷清单。
- 纯 Python 3 标准库、脚本位置无关、默认离线。

## 快速开始

```bash
# 正式契约路径（/input -> /app/work -> /app/output）
python3 scripts/refgraph.py --roots /input --workdir /app/work
python3 scripts/snowball.py --case /input/case.json --task /input/task.md \
    --workdir /app/work --out /app/output
python3 scripts/verify_trace.py

# 本地合成示例（全部虚构文献，DOI 形如 10.0000/synth.*）
python3 scripts/refgraph.py --roots examples/corpus --workdir examples/run_out
python3 scripts/snowball.py --graph examples/run_out/graph.json \
    --case examples/case.json --task examples/task.md \
    --out examples/run_out --workdir examples/run_out \
    --max-depth 4 --max-branch 2 --year-min 2000 --classic-citedby 1000
python3 scripts/verify_trace.py --graph examples/run_out/graph.json \
    --result examples/run_out/result.json --trace examples/run_out/trace_graph.json \
    --case examples/case.json
```

## 目录结构

```
SKILL.md                      # Skill 说明（面向 Agent，含三命令管线与运行契约）
GITHUB_URL.txt                # GitHub 作品链接
scripts/
  refgraph.py                 # 建图：扫描/解析/规范化/去重/前向边反向恢复
  snowball.py                 # 追踪：种子解析、方向感知 BFS、剪枝与停止、交付
  verify_trace.py             # 自查：locator/方向/悬空节点/契约镜像门禁
references/
  traversal_policy.md         # 扩展/剪枝/停止规则全文
  direction_semantics.md      # 方向语义与反向索引恢复的可靠性说明
examples/
  corpus/crossref_batch.json      # 合成语料（Crossref 风格，5 篇虚构文献）
  corpus/europepmc_results.json   # 合成语料（EuropePMC 风格，3 篇虚构文献）
  case.json                       # 合成案例（含 output_contract）
  task.md                         # 合成任务说明
  walkthrough.md                  # 示例运行实录与预期要点
  run_out/                        # 合成示例的真实运行产物（graph/result/trace）
```

## 合成示例声明

`examples/` 下所有文献、DOI（`10.0000/synth.*`）、作者、期刊均为**虚构**
（SYNTHETIC, not real papers），仅用于演示管线；`run_out/` 是作者在本机上
对该合成示例真实执行三命令管线得到的产物，**非正式案例结果**。
