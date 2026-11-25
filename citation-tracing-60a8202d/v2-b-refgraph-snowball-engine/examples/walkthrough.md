# 合成示例运行实录（SYNTHETIC / 合成示例，非正式案例结果）

> **合成示例 / SYNTHETIC, not real papers。** 本目录所有文献、DOI
> （`10.0000/synth.*`）、作者、期刊均为虚构，仅用于演示管线。
> `run_out/` 是作者在本机（macOS, Python 3.12）对这份合成语料**真实执行**
> 三命令管线得到的产物，不是预先写好的答案，也不是正式案例结果。

## 语料设计（8 篇虚构文献 + 1 个语料外引用目标）

| DOI | 年 | 角色 |
|---|---|---|
| 10.0000/synth.seed-2021 | 2021 | **种子**（Crossref 文件，只给参考文献） |
| 10.0000/synth.classic-1998 | 1998 | 奠基经典，被引 4820（触发经典例外） |
| 10.0000/synth.beta-2015 | 2015 | 种子后向第 1 层；其参考文献引出第 2 层 |
| 10.0000/synth.alpha-2005 | 2005 | 第 2 层后向节点 |
| 10.0000/synth.noise-2020 | 2020 | 主题无关（贝类脂质组学），触发关键词剪枝 |
| 10.0000/synth.delta-2022 | 2022 | EuropePMC 文件，引用种子 → 前向第 1 层 |
| 10.0000/synth.epsilon-2023 | 2023 | 引用种子与 delta → 前向第 1 层 |
| 10.0000/synth.theta-2023 | 2023 | 引用种子但相关性低 → 触发分支上限剪枝 |
| 10.0000/synth.unresolved-2010 | — | 只在 beta 参考文献中出现 → 诚实 stub |

种子所在记录只有参考文献（Crossref 风格），施引它的三篇在另一个文件
（EuropePMC 风格）里——因此种子的全部前向边必须经**反向索引恢复**
（`direction_restored: true`）。

## 实际运行命令与退出码

```bash
# 在 bundle 根目录执行；退出码全部为 0
python3 scripts/refgraph.py --roots examples/corpus --workdir examples/run_out
python3 scripts/snowball.py --graph examples/run_out/graph.json \
    --case examples/case.json --task examples/task.md \
    --out examples/run_out --workdir examples/run_out \
    --max-depth 4 --max-nodes 250 --max-branch 2 --year-min 2000 \
    --classic-citedby 1000
python3 scripts/verify_trace.py --graph examples/run_out/graph.json \
    --result examples/run_out/result.json --trace examples/run_out/trace_graph.json \
    --case examples/case.json
```

## 运行产物要点（run_out/，目检确认）

- `graph.json`：9 节点（8 记录 + 1 stub）、24 边（12 backward + 12 forward，
  12 条前向边全部 `direction_restored: true`）、2 个文件均解析 ok。
- `result.json`：`status = ok`，`case_id = SYNTH-DEMO-001`，output_contract
  全部 11 个字段逐字段镜像（verify 校验通过）。
  - 层级：L1 = {classic, beta, delta, epsilon}（后向 2 + 前向 2）；
    L2 = {alpha, unresolved-stub}；L3 零新增。
  - `pruning_log` 四条决策：
    1. classic-1998：`kept / classic_exception`（1998 < 2000 但被引 4820 ≥ 1000）；
    2. noise-2020：`pruned / keyword_irrelevant`；
    3. theta-2023：`pruned / branch_cap`（种子前向分支 3 选 2，得分最低出局）；
    4. unresolved-2010：`kept / kept_stub`（诚实 stub，仅 locator）。
  - `stop_log`：`zero_growth_layer`（depth 3 整层零新增，自然停止，
    未触及 max-depth 4）。
- `trace_graph.json`：7 节点、20 边的追踪子图，节点带 layer/directions/
  stub/classic 标注。
- verify 输出摘要：`ok=true`，0 errors，0 warnings，defects 为空
  （退出码 0）。

四项演示目标全部真实触发：多层级扩展（L0–L2）、分支剪枝（关键词 + 分支上限）、
前向边反向恢复（12 条 direction_restored）、整层零新增停止。
