---
name: search-strategist
description: 预算感知的序贯实验搜索策略器。当任务要求在给定实验点预算内决定"在哪些参数组合做实验、每轮做多少、何时停止"且整条搜索链必须可独立复核复现时触发；输出带固定随机种子的分阶段搜索计划与追加式决策日志。
---

# search-strategist — 预算感知序贯搜索与可复核收敛判据

## 定位声明

本技能只决定三件事：**在哪做实验、做多少、何时停**。

- 它**不**拟合代理模型（无高斯过程、无贝叶斯优化），**不**预测响应值，**不**核算金钱/时间成本；
- 它把"候选点怎么产生、每轮补哪些点、什么时候停、停在哪一步"全部落成**确定性记录**：固定随机种子驱动候选生成，每次决策追加到带 sha256 摘要的 JSONL 决策日志，第三方可用 `search_log.py verify` 独立重放；
- 目标读者是因"搜索策略没有收敛依据"而失败的实验参数优化任务：候选点来源说不清、停止判据缺失、换个人复现不出同一套建议。

## 何时使用 / 不适用

**使用**：

- 输入包含可解析的参数空间（每参数 lower/upper/step，连续或离散）+ 实验点预算 + （可选）已有历史点数；
- 需要网格 / 序贯设计 / 分阶段筛选之间的**有依据的选择**，且停止判据必须事先声明、事后可验；
- 评测或审计要求"给定同一输入，任何人重跑出同一套建议"。

**不适用**：

- 参数空间无法解析或预算完全未给（先澄清，不要猜）；
- 需要在线模型预测来选点（贝叶斯优化、主动学习）——本技能刻意不用，见 `references/strategy-playbook.md`；
- 多目标冲突、带安全约束的实时闭环控制——超出范围，如实报 partial。

## 固定命令顺序

所有脚本仅用 Python 3 标准库、无网络。任何非法输入都以 JSON 错误对象 + 非零退出码结束，**绝不 traceback**。

```bash
# 1. 生成搜索计划（同参数同种子 => 逐字节一致）
python3 scripts/plan_search.py --space param_space.json --budget 10 \
    --history 0 --seed 20240611 --output search_plan.json

# 2. 每完成一批实验后：判定 STOP 或给出下一批候选点，并追加决策日志
#    （results.csv 必须含表头 round,<每个参数名>,response；文件不存在 = 尚未做实验）
python3 scripts/next_batch.py --plan search_plan.json --results results.csv \
    --log decision_log.jsonl --output next_batch.json

# 3. 任何时候：重放决策日志做第三方复核
python3 scripts/search_log.py verify --log decision_log.jsonl \
    --results results.csv --output verify_report.json
```

`search_log.py` 也可单独追加人工决策：

```bash
python3 scripts/search_log.py append --log decision_log.jsonl --round 1 \
    --points-json '[{"temperature":400,"time":3.5,"flow":180}]' \
    --results-json '@results_snapshot.json' --decision "EMIT 人工补点" \
    --criteria-json '{"budget_exhausted":{"triggered":false}}'
```

## 工作流程（含预算分配）

1. **读取与校验**：解析参数空间 JSON（`objective` 缺省 maximize）、预算、历史点数、种子（缺省 2024）。
2. **策略选择**（显式决策表，逐条写入 search_plan.json）：

   | 规则 | 条件 | 策略 |
   |---|---|---|
   | 1 | budget ≤ 0 | `none`（零轮次，只登记历史点） |
   | 2 | 可行组合总数 ≤ budget | `full_grid`（全网格，候选点全部列出） |
   | 3 | 0 < budget < 4 | `screening_only`（种子化 LHS 花光预算，跳过确认轮） |
   | 4 | 其他 | `staged_sequential`（三阶段，见下） |

3. **预算分配**（规则 4）：筛选轮 = max(2, round(0.4 × budget))；确认轮 = max(2, round(0.2 × budget))，且 ≥2 次重复；局部加密轮 = 剩余全部。budget=10 → 4 / 4 / 2。
4. **序贯执行循环**：调用 `next_batch.py` → 若 EMIT 则按给出的坐标做实验、把结果追加进 results.csv → 再调用，直到 STOP 或预算耗尽。各轮职责：
   - **轮 1 筛选**：种子化拉丁超立方（`random.Random(seed)` 分层抽样，吸附到各参数 step 网格，确定性去重），候选点**全部数值确定**地写在计划里；
   - **轮 2 局部加密**：围绕当前最优点做坐标式有限差分步进（固定维度顺序，先 −step 后 +step，越界裁剪，剔除已评估点，取前 N 个；全部重复时回退到最近未访问网格点）；
   - **轮 3 确认性重复**：对最优点做 ≥2 次同坐标重复（不同 replicate 编号）估计噪声。
5. **停止判据**（每条都在决策日志里记录触发状态，详见 `references/stopping-criteria.md`）：
   `budget_exhausted`（预算耗尽）/ `low_improvement`（连续两个搜索轮最优点相对改进 < 2%；若在进入确认轮前触发，则确认重复作为待确认事项列出而非执行）/ `boundary_constrained`（最优点在所有维度抵近约束边界 1 个步长以内）/ `all_candidates_duplicate`（全部候选点重复且无未访问回退点）。
6. **落盘 result.json**（见下节契约）；预算或时间将尽时，优先落盘**诚实的 partial**：已完成的轮次、已验证的日志、未完成的确认项，绝不编造。

## 输出物说明表

| 输出物 | 产生者 | 内容 |
|---|---|---|
| `search_plan.json` | plan_search.py | 策略与理由、决策表、各轮候选点/生成规则、每轮停止判据、复现种子、重放说明 |
| `results.csv` | 实验方 | 表头 `round,<参数名...>,response`；本技能只读不改 |
| `next_batch.json` | next_batch.py | `status`（CONTINUE/STOP）、触发的判据、下一批候选点与理由、判据状态快照、日志序号 |
| `decision_log.jsonl` | next_batch.py / search_log.py | 追加式决策日志；每条含 `seq`（从 1 单调递增）、`round`、`points`、`results` 快照、`results_digest`（sha256）、`decision`、`criterion_states` |
| `verify_report.json` | search_log.py verify | 重放结论：seq 单调性、digest 一致性、与 results.csv 交叉核对、问题清单 |
| `result.json` | Agent | 挑战输出契约（下节） |

## result.json 契约（写 /app/output/result.json）

- `case_id`：**照抄** `/input/case.json` 的 `case_id`；
- `output_contract` 全部字段：**动态读取** case.json 的 `output_contract` 列表，逐字段填充，一个都不许漏（无法填充就如实写 partial 并说明）；
- `status`：诚实四选一 `success` / `partial` / `unable_to_determine` / `refused`；搜索没跑完、判据未触发、材料缺失都只能 partial 或更低；
- `sources`：引用过的全部文件/材料路径；
- `uncertainty`：噪声估计依据、判据阈值、未排除的失效场景；
- 变更记录：每次策略决策与日志验证结果的流水账。

## 异常处理表

| 异常 | 行为 | 退出码 |
|---|---|---|
| 预算为 0 / 负数 | 计划策略 `none`、零轮次、登记历史点数；next_batch 立即 `STOP no_budget` | 0 |
| 参数空间不可解析（坏 JSON / 缺字段 / step ≤ 0 / lower ≥ upper / 重名） | 输出 JSON 错误对象说明具体字段 | 2 |
| 结果文件缺列（少 `round`/某参数/`response`） | 报错并列出缺失列与完整必需列清单；非数值行跳过并计入 warnings | 3 |
| 全部候选点重复 | 回退到"距最优点最近的未访问网格点"（确定性扩展扫描）；仍无 → `STOP all_candidates_duplicate` | 0 |
| 预算 < 4 的组合爆炸空间 | 降级 `screening_only`，理由写入计划 | 0 |
| 决策日志损坏 | 拒绝追加，报错（宁可中断也不污染可复核链） | 2 |
| 任何未预料异常 | 兜底 JSON 错误对象，绝不 traceback | 2 |

## 合成示例说明

`examples/` 内置一个**完全合成**的端到端演示（响应面是二次函数 + 基于 sha256 的小噪声的"合成 oracle"，不代表任何真实体系）：3 参数空间（温度 300–500°C step 10、时间 1–6 h step 0.5、流量 50–300 mL/min step 10，共 6006 组合）、预算 10 点。运行 `python3 examples/run_demo.py` 会重新生成 `examples/synthetic-output/` 的全部产物：分阶段计划 → 逐轮"做实验"直到 STOP → 日志重放通过（`verify_report.json`）→ 篡改 digest 后重放被抓（`verify_tampered.json`，退出码 1）→ 同种子重跑计划逐字节一致（`determinism_check.json`）→ 契约式 `result.json`。命令与字段解释见 `examples/README.md`。

## 局限

- 局部加密是坐标式步进，对强交互项/旋转谷地收敛慢；2% 改进阈值在平台区可能过早停（已知失效场景见 references）；
- 无代理模型 ⇒ 无法给出未测点的预测区间，也不利用历史点拟合先验；
- LHS 筛选点数少时可能漏掉窄最优区；确认轮 ≥2 次重复只能给粗噪声估计；
- 单目标；约束只支持矩形边界（lower/upper/step）；
- 确定性 = 可复核性的代价：放弃贝叶斯优化的样本效率，换取标准库可实现、第三方可逐字节重放（权衡论证见 `references/strategy-playbook.md`）。

## 参考文件

- `references/strategy-playbook.md` — 网格/筛选/局部加密/贝叶斯优化的适用条件决策表
- `references/stopping-criteria.md` — 每条停止判据的定义、触发条件与已知失效场景
