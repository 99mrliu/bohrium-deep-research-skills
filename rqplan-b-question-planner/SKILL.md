---
name: rqplan-question-planner
description: 科研问题的"结构化拆解 + 检索规划 + 收敛停止判据"引擎——把复杂研究问题拆成带验收标准的可检索子问题 DAG（对象/机制/方法/时间窗/证据要求六要素），编译为分波次查询计划（前置先行、同层并行、缺口补检），执行中以 append-only 轮次日志记账，自动做逐子问题饱和检测并给出可解释的停止决定（证据充分/边际收益过低/转人工），最后产出 SQ×来源覆盖矩阵与按 output_contract 生成的 result.json。Use when a task gives a research question (possibly with a finite local snapshot / search exports) and the job is to decompose it into sub-questions, plan and order the retrieval rounds, know when to stop, and leave a replayable audit trail (问题拆解, 查询规划, 停止条件, 饱和检测, 覆盖矩阵, 检索收敛).
---

# 问题拆解与检索规划器（rqplan-question-planner）

## 何时使用

案例给出一个复合科研问题（含对象、机制/干预、方法、时间范围、比较关系、证据要求中的多项），需要把它拆成可独立检索的子问题、安排检索顺序、控制轮次并在证据充分时收敛。本方向的增益在**前端**：拆解与规划的确定性框架 + 停止判据；检索动作本身由 Agent 按生成的计划执行并记账。

## 运行方式（两步规划 + 边检索边记账 + 收尾）

```bash
# 1) 写拆解: 读 /input/case.json 与 /input/task.md 后,严格按
#    resources/decomposition_schema.md 写 /app/work/decomposition.json(这是全流程
#    唯一一次模型创作,先写草稿再校验):
python3 /skills/weekly-skill/scripts/decompose_check.py \
    --case /input/case.json --input-dir /input \
    --decomposition /app/work/decomposition.json          # 不存在则输出模板与逐项要求

# 2) 编译计划(波次 DAG + 预算 + 停止规则):
python3 /skills/weekly-skill/scripts/plan.py \
    --decomposition /app/work/decomposition.json --work /app/work

# 3) 按 /app/work/retrieval_plan.json 逐条执行检索;每完成一轮立即记一笔(顺序不可事后补):
python3 /skills/weekly-skill/scripts/roundlog.py append --work /app/work \
    --sq SQ-1 --query "..." --source search09_export.json \
    --returned 12 --new-relevant 3 --note "首轮宽检索"

# 4) 每波结束看收敛状态;脚本自动判定每 SQ 是否饱和并给出全局停止决定:
python3 /skills/weekly-skill/scripts/roundlog.py status --work /app/work

# 5) 停止后: 覆盖矩阵 + 缺口分类 + 收尾 result.json:
python3 /skills/weekly-skill/scripts/coverage.py --case /input/case.json --work /app/work
python3 /skills/weekly-skill/scripts/finalize.py --case /input/case.json --work /app/work --out /app/output
```

**预算意识**：模型请求大头只有第 1 步（1–2 次）；检索执行只追加日志（0 次模型请求）；停止由脚本判据裁决，不靠"感觉够了"。先跑通第 1–2 步产出 partial 产物，再执行检索。

## 拆解要求（decomposition_check.py 强制校验）

- 每个子问题 SQ-n 必须含：`facet`（六要素标注：object/mechanism/method/timeframe/comparator/evidence）、`question`（一句可回答的问句）、`acceptance`（什么证据算回答了它，如"≥2 篇原始研究给出定量指标"）、`queries`（中英各 ≥1 条检索式）、`depends_on`（空=可并行前置）。
- 硬性校验：≥2 且 ≤12 个 SQ；depends_on 无环、无悬空引用；每个 SQ 有非空 acceptance 与 queries；时间窗只允许出现在 ≤1 个 SQ 的检索式中（其余引用，避免重复过滤）。
- 校验失败时脚本输出**逐项诊断**，修正后重跑；不允许带病进入规划。

## 计划编译（plan.py）

- 波次结构：W1 定界（检索输入快照索引/背景，1–2 动作）→ W2 主检索（按 DAG 分层，同层动作并行编号）→ W3 缺口补检（仅当 coverage 显示某 SQ 未达标时启用）。
- 每个检索动作：`query`、`source`（输入文件或检索工具）、`dedup_key`（DOI 或 首作者+年份+标题前缀）、`stop_rule`（相关命中 ≥K 或连续 2 轮新增相关 = 0）、`budget_calls`。
- 总预算表：默认检索动作 ≤ 15、模型请求 ≤ 60；超出预算的动作被标 `deferred`，由停止判据决定是否值得追加。

## 轮次日志与停止判据（roundlog.py，规则见 resources/stop_rules.md）

- append-only JSONL：每轮记录 sq、查询式、来源、返回数、新增相关数、证据 rid 列表、备注、时间戳；支持 `verify`（重放完整性）。
- 饱和检测：某 SQ 连续 2 轮 `new_relevant=0` → 该 SQ 标 saturated；全部 SQ 达到 acceptance 或 saturated → 全局 `stop: evidence_sufficient`。
- 连续 2 轮全局新增相关为 0 且有 SQ 未达标 → `stop: marginal_gain_low`，未达标 SQ 进入缺口分析；检索连续异常（接口失败）≥2 次 → `stop: handoff_to_human`。
- 每轮 `status` 输出当前判定与理由，全部理由可独立复核。

## 覆盖矩阵与缺口（coverage.py）

- 行=SQ，列=来源/波次；单元格=达标(satisfied)/未达标(gap)/未检索(not_searched)/饱和无新增(saturated)。
- 缺口只从矩阵导出：`searched_but_absent`（检索过且饱和仍无证据）=高置信研究空白；`not_searched`=无法判断，禁止凭印象写空白。
- 输出 `coverage_matrix.json`、`gap_analysis.json`（含逐 SQ 停止理由链）。

## 输入 / 输出

- 输入：`case.json`、`task.md`、可选快照文件（检索源在计划中以实际存在的输入文件为准，不存在的源标 `unavailable`）。
- 输出（`/app/output`）：`result.json`（按 output_contract；含 subquestions、evidence_log=轮次日志指针、coverage、gap_analysis、status、uncertainty）、`coverage_matrix.json`；`/app/work`：`decomposition.json`、`retrieval_plan.json`、`rounds.jsonl`。

## 依赖与异常处理

- 仅 Python 3 标准库。检索动作失败：append 一笔 `status=failed` 并继续下一动作，失败原因入备注。
- 输入缺失 case.json：decompose_check 输出模板与 blocked 提示；finalize 输出 `status=blocked` 的 result.json。
- 停止判据与人工意见冲突时：以判据为准并在 uncertainty 中记录分歧；绝不为了"多查几轮"突破预算上限。

## 不适用边界

- 不做逐条记录的去重与纳排台账（属筛查方向）、不做快照内排序打分（属检索方向）；本方向消费它们的产物作为证据 rid。
- 不预制任何案例答案；拆解与结论全部来自本次运行。

## 最小调用示例（示意输出，非正式案例结果）

```bash
python3 .../decompose_check.py --case /input/case.json --input-dir /input --decomposition /app/work/decomposition.json
# 首次: {"ok": false, "error": "decomposition 不存在", "template": "已打印六要素模板,请按 schema 填写"}
# 填好后: {"ok": true, "sqs": 4, "dag_layers": 3}
python3 .../plan.py --decomposition /app/work/decomposition.json --work /app/work
# {"ok": true, "waves": 3, "actions": 9, "budget": {"calls": 15, "deferred": 0}}
python3 .../roundlog.py append --work /app/work --sq SQ-2 --query "..." --returned 10 --new-relevant 2
python3 .../roundlog.py status --work /app/work
# {"stop": false, "saturated": ["SQ-3"], "reason": "SQ-1/SQ-2 未达 acceptance,继续 W2"}
python3 .../coverage.py --case /input/case.json --work /app/work
python3 .../finalize.py --case /input/case.json --work /app/work --out /app/output
# {"ok": true, "status": "partial", "stop_decision": "marginal_gain_low", ...}
```
