---
name: cost-ledger
description: 实验参数优化中的成本台账技能。当任务要求把机时、耗材、样品数与通量纳入候选方案权衡、需要带算术痕迹的成本表与成本-响应 Pareto 推荐时触发；只负责成本-时间-通量核算与权衡陈述，不选参数、不建响应模型。
---

# cost-ledger — 成本口径、单位自洽与成本-响应 Pareto 权衡的真实算术

## 1. 定位声明（务必先读）

本技能**不选择实验参数、不构建响应模型、不预测响应值**。它只做一件事：
把候选方案版本的成本-时间-通量账目变成**可复算的算术链**，并在预算与截止
约束下给出成本-响应 Pareto 权衡陈述。

它针对的典型失败：Agent 只盯响应指标，给出的"最优解"在真实实验室做不起；
或成本数字口径混乱（小时/分钟混用、漏算重复实验与样品制备、漏乘 runs 数）。
本技能的铁律：**口径不自洽宁可拒算，绝不静默换算**；每一笔账必须带算术痕迹。

预测响应值一律来自候选方案自带字段，本技能只做比较与权衡，不为其准确性背书。

## 2. 何时使用 / 不适用

**何时使用（触发条件）**
- 任务给出多个候选实验方案版本，要求比较成本、周期、通量或"性价比"；
- 案例材料含资源/价格/预约契约（机时费率、耗材单价、每日机时、预算、截止）；
- 任务要求"在预算内""在截止日期前""成本-性能权衡""Pareto"等表述；
- 需要给实验计划附上可审计的成本表与取舍陈述。

**不适用**
- 需要设计实验点、选择参数水平、拟合响应面/贝叶斯优化——那是参数优化技能的
  职责；本技能只核算别人给出的方案版本；
- 材料中完全没有成本/资源信息且任务也不要求成本权衡——不要强行造账；
- 需要真实报价或采购决策——本技能处理的契约是**前瞻性计划数据**（见第 9 节
  局限），不能替代询价。

## 3. 运行契约（Harness 环境）

评测方把技能安装到 `/skills/weekly-skill`，用官方 DeepSeek Harness 在 3 个固定
科研案例上运行加载本技能的 Agent：

- 运行时输入：`/input/case.json`（含 `case_id`、任务描述、`output_contract`
  字段清单、材料路径；案例含前瞻性的资源/价格/预约契约与每案例多版本候选方案，
  要求真实算术与必要校验）、`/input/task.md`、案例材料；
- 工作目录：`/app/work`；最终结果写 `/app/output`，必须含 `result.json`：
  - `case_id`：照抄输入 case.json；
  - `output_contract` 的全部字段：**动态读取 case.json 的 output_contract
    清单**，逐个填充，不得硬编码字段名；
  - `status`：`success / partial / unable_to_determine / refused`，必须诚实——
    单位被拒、契约缺字段、无可行方案时都不得报 success；
  - `sources`：实际读取过的材料路径；
  - `uncertainty`：所有假设、缺失、拒算原因；
  - 变更记录（change_log）：记录每一步脚本调用与其 status；
- 预算约 **64 次模型请求 / 900 秒**：脚本调用本身秒级完成，模型请求主要用于
  读题、解读产物与撰写陈述。**尽早落盘诚实 partial**：见第 5 节预算分配。

## 4. 固定命令顺序（不要打乱）

```bash
SKILL=/skills/weekly-skill            # 技能安装路径
W=/app/work                           # 工作目录

# 步骤 1：解析成本模型（契约优先，材料文本兜底；单位不自洽则 exit 2 拒绝）
python3 $SKILL/scripts/cost_model.py \
  --case /input/case.json \
  --contract <契约JSON路径，可省，缺省从 case.json.materials 推断> \
  --materials <材料目录，可省> \
  --out $W/cost_model.json

# 步骤 2：逐版本成本核算（仅当步骤 1 非 refused/error）
python3 $SKILL/scripts/plan_costing.py \
  --cost-model $W/cost_model.json \
  --plans <候选方案版本JSON> \
  --out $W/cost_sheet.json

# 步骤 3：成本-响应 Pareto 前沿与推荐
python3 $SKILL/scripts/pareto.py \
  --cost-sheet $W/cost_sheet.json \
  --out $W/pareto.json
```

规则：
- 上游 status 为 refused/error 时**不得**继续跑下游脚本；把上游 reason 透传进
  result.json 的 uncertainty，status 如实报 refused 或 partial；
- 三个脚本均仅用 Python 3 标准库、无网络；退出码：0 ok/partial，2 单位拒算，
  3 数值非法/输入结构非法/上游不可用，1 内部错误（仍会尽量落盘错误 JSON，
  任何输入不得 traceback）；
- 脚本产物是 result.json 的证据来源：算术结论**只能**引用产物中的数字，
  不得心算改写。

## 5. 工作流程（含预算分配）

模型请求预算分配（总计 ≤64 次）：

| 阶段 | 请求预算 | 动作 |
|---|---|---|
| 读题与定位材料 | ≤ 8 | 读 case.json / task.md，动态提取 output_contract 清单与材料路径；确认契约与方案版本文件位置 |
| 成本模型解析与校验 | ≤ 8 | 跑步骤 1；若 refused/partial，读 uncertainty 决定是否可补救（如换材料路径重试一次） |
| 三版本核算与核对 | ≤ 15 | 跑步骤 2；**人工复核至少一条算术痕迹**（取一个版本，手算 total_cost 与 trace 数字比对） |
| Pareto 与权衡陈述 | ≤ 10 | 跑步骤 3；核对推荐版本与取舍陈述数字来自产物 |
| 组装 result.json | ≤ 13 | 按 output_contract 逐字段填充；sources/uncertainty/change_log 齐全 |
| 预留 | ≥ 10 | 异常重试、重新读题、最终校验 |

时间纪律：脚本总耗时 < 5 秒；若已用 > 40 次请求或 > 600 秒仍未完成步骤 3，
**立即**用已有产物落盘 status=partial 的 result.json，再用剩余预算改进。

## 6. 输出物说明表

| 产物 | 生成者 | 内容 |
|---|---|---|
| cost_model.json | cost_model.py | 成本模型：每量带显式声明单位、来源、已应用换算记录、uncertainty |
| cost_sheet.json | plan_costing.py | 逐版本成本表：总机时/总耗材/总成本/总历时(工作日)/通量(样品/天)，每行带 formula+代入数字的算术痕迹，within_budget / within_deadline verdict |
| pareto.json | pareto.py | 成本-响应 Pareto 前沿、被支配标注、预算约束下推荐版本与取舍陈述 |
| /app/output/result.json | Agent 组装 | case_id（照抄）+ output_contract 全部字段 + 诚实 status + sources + uncertainty + 变更记录 |

## 7. 异常处理表

| 异常 | 脚本行为 | Agent 应对 |
|---|---|---|
| 契约字段缺失 | 先用材料文本兜底（只认同义单位写法）；仍缺 → status=partial 并记 uncertainty | result.json 报 partial，把缺失字段列入 uncertainty 与确认事项 |
| 单位不自洽（如"分钟"对声明"小时"且无换算白名单） | cost_model.py 拒绝，exit 2，产物含原因；plan_costing.py 对单位不符的版本标记 rejected，全拒则 exit 2 | **不得**自行心算换算后继续；result.json 报 refused/partial，原文引用拒绝原因 |
| 预算为负 / 每日机时非正 / 截止非正 | cost_model.py 拒绝，exit 3 | 报 refused，指出契约数值非法，要求人工确认契约 |
| 方案版本为空 | plan_costing.py 输出 status=partial 空表，exit 0 | 报 partial：无方案可核算；不得伪造默认方案 |
| 版本缺 predicted_response | 该版本正常核算成本，但不参与 Pareto，记 uncertainty | Pareto 结论注明该版本仅成本可比 |
| 无可行版本（全部超预算/超期） | pareto.py recommendation=null，status=partial | 报 partial，列出最接近可行的版本与缺口（超多少元/几天） |
| 任何意外输入 | 脚本捕获一切异常，落盘 error JSON，exit 1，绝不 traceback | 把 error 写入 uncertainty，报 partial/refused |

## 8. result.json 契约（组装规则）

1. `case_id` 逐字照抄 `/input/case.json`；
2. 读取 case.json 的 `output_contract` 数组，**逐个字段**在 result.json 顶层
   给出对应内容（例如含 experiment_plan / evidence_and_risk /
   confirmation_items 时，三者都必须出现）；字段内容中的每个成本/时间数字
   必须能在 cost_sheet.json 或 pareto.json 中找到原值；
3. `status` 诚实分级：全链路 ok 且人工复核通过 → success；任一环节 partial
   （缺字段、部分版本被拒、无可行方案）→ partial；单位拒算或契约非法 →
   refused；材料完全无法支撑任何核算 → unable_to_determine；
4. `sources` 列实际读取的文件；`uncertainty` 汇总三个产物中的 uncertainty
   加上"价格为前瞻性计划数据"的声明；变更记录列出每次脚本调用的命令、
   退出码与产物 status。

## 9. 合成示例与局限

**合成示例**：`examples/` 含完整端到端合成案例（机时 180 元/h、耗材 45 元/份、
每日 6 h、预算 8000 元、截止 10 个工作日；v1 全网格 27 点 / v2 序贯 10 点 /
v3 筛选 6 点），复现命令见 `examples/README.md`。其中 v1 核算为 14580.00 元、
12 个工作日，被正确标记 within_budget=false；另含负例：单 run 机时单位写成
"分钟"的契约变体被 cost_model.py 拒绝（exit 2，产物 unit_reject.json）。

**局限（必须在 result.json 中如实声明）**
- 案例中的资源/价格/预约契约是**前瞻性计划数据，不是真实报价**；本技能的
  成本结论只能作为计划参考，不能作为采购或结算依据；
- 预测响应值来自候选方案自带字段，本技能不验证其统计可靠性；
- 历时按机时预约窗口口径（每日可用机时、向上取整）计算，样品制备时间单列、
  不计入工作日；排队、设备维护、失败重做等现实扰动未建模；
- 文本兜底解析只覆盖规范中列出的同义单位写法，复杂表述需人工确认。
