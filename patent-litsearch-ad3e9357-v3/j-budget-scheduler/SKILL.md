---
name: budget-aware-verification-scheduler
description: 当核验流水线必须在硬性预算（模型请求数／秒数／token 数）内完成、且要求过程可调度、可断点续跑、可审计、预算不足时可显式降级止损时，应使用本技能对核验任务队列进行预算感知的过程质量控制，尤其适用于预算受限的专利与技术文献检索核验场景。
---

# 预算感知核验调度器（budget-aware-verification-scheduler）

## 用途与适用条件

本技能解决的唯一问题是**过程经济与预算调度**：在核验任务多、预算硬的条件下，让核验过程本身可调度、可检查点化、可审计。它提供五件工具（均为 Python 3 标准库脚本，退出码 0 正常 / 1 违反 / 2 用法错误）：

1. **仅追加式预算账本**（`scripts/budget_ledger.py`）：把 plan / spend / checkpoint / degrade 事件追加进 `ledger.jsonl`；每行携带 `prev_hash` 与 `line_hash`（sha256 链），`state` 子命令纯粹从账本重算 `budget_state.json`，`verify` 子命令校验整链。
2. **确定性调度器**（`scripts/plan_schedule.py`）：读任务队列、预算状态与策略文件，按文档化贪心规则（强制任务优先，其次优先级/成本比，依赖序严格满足）输出 `plan.json`；**第 0 步永远是诚实部分骨架的检查点写入**，使可交付物从第一分钟就存在；每个决策都标注所触发的规则。
3. **检查点**（`scripts/checkpoint.py`）：写入/恢复 result.json 草稿哈希、已完成项、待办队列与链式 `state_hash`；恢复时重算校验，篡改即退出码 1，绝不静默续跑。
4. **降级计划**（`scripts/degrade_plan.py`）：剩余预算低于阈值时，只填 output_contract 强制字段，其余置 null 并登记 uncertainty，同时产出 `degradation_report.json`，逐项说明被放弃的核验及其后果。
5. **成本报告**（`scripts/cost_report.py`）：运行结束把账本折叠为逐步骤核算 JSON 与中文 Markdown 摘要（利用率、跳过原因），可直接摘录进 result.json 的 `change_records` / `uncertainty`。

所有调度决策都是确定性的、可从账本重放复核的；模型负责编排调用，**绝不凭记忆估计成本**——成本只来自队列中的估计值、策略文件的缺省值与账本中的实际花费。

## 运行时契约

- 评测方将本技能安装于 `/skills/weekly-skill`，以官方 DeepSeek Harness 在 3 个固定隐藏案例上运行。
- 输入位于 `/input/`：`case.json`、`task.md` 与案卷材料（6 条专利记录、3 份 USPTO 传真原件 PDF、对比论文；号码/主题检索式；溯源定位的权利要求版本；官方法律状态未知——须如实声明；观察到的链接并非穷尽同族；WO 合并 OCR 边界予以保留）。**必须读取真实文件内容，绝不从文件名推断。**
- 工作目录 `/app/work`；交付物 `/app/output/result.json`，须包含：逐字保留的 `case_id`；诚实的 `status`（ok / partial / failed）；`sources`（路径 + sha256）；`uncertainty`；`change_records`；并**镜像 output_contract 的全部字段**（未填写者置 null 并登记 uncertainty）。
- 硬预算：64 次模型请求 / 900 秒 / 每次响应 16384 token；本技能正是这一纪律的操作化实现。
- 绝不捏造；部分完成的结果必须如实点名其局限。

## 调用方式（有序流水线）

以下命令假定工作目录为 `/app/work`，夹具路径以本技能安装目录为例；正式运行时以真实 case 的 `output_contract` 与任务队列替换合成夹具。

```bash
SKILL=/skills/weekly-skill
WORK=/app/work
mkdir -p "$WORK"

# 0) 以 case 的 output_contract 构建任务队列 task_queue.json
#    （每项：id, kind, priority, est_cost{requests,seconds,tokens}, deps[],
#      mandatory 由 output_contract 字段的 mandatory 标志派生, covers[]）

# 1) 从账本重算预算状态（账本不存在时视为全新预算 64/900/16384）
python3 $SKILL/scripts/budget_ledger.py state \
  --ledger $WORK/ledger.jsonl \
  --policy $SKILL/examples/fixtures/scheduling_policy.json \
  --out $WORK/budget_state.json

# 2) 生成确定性执行计划（第 0 步必为检查点写入）
python3 $SKILL/scripts/plan_schedule.py \
  --queue $WORK/task_queue.json --state $WORK/budget_state.json \
  --policy $SKILL/examples/fixtures/scheduling_policy.json \
  --out $WORK/plan.json
#   （推荐把计划事件含 skipped 清单一并入账，供成本报告归集跳过原因）
python3 $SKILL/scripts/budget_ledger.py append --ledger $WORK/ledger.jsonl \
  --kind plan --payload '{"plan_file":"plan.json","mode":"normal","skipped":[]}'

# 3) 第 0 步：立即写入诚实部分骨架检查点
#    （若要把 checkpoint 事件入账，须在写入检查点【之前】追加，
#      使检查点锚定包含该事件的账本链头，否则 restore --ledger 会拒绝）
python3 $SKILL/scripts/budget_ledger.py append --ledger $WORK/ledger.jsonl \
  --kind checkpoint --payload '{"checkpoint_file":"checkpoint.json"}'
python3 $SKILL/scripts/checkpoint.py write --workdir $WORK \
  --result $WORK/result_draft.json --completed $WORK/completed.json \
  --pending $WORK/pending.json --ledger $WORK/ledger.jsonl

# 4) 按计划逐项执行核验；每项完成后把实际花费入账
python3 $SKILL/scripts/budget_ledger.py append --ledger $WORK/ledger.jsonl \
  --kind spend --payload '{"step_id":"v01","requests":4,"seconds":62,"tokens":720}'

# 5) 每完成若干项：重算状态并重新规划（中断后用 restore 精确续跑）
python3 $SKILL/scripts/checkpoint.py restore --workdir $WORK --ledger $WORK/ledger.jsonl

# 6) 若计划转为 degrade 模式：生成降级计划与降级报告
python3 $SKILL/scripts/degrade_plan.py \
  --state $WORK/budget_state.json --contract /input/case.json \
  --queue $WORK/task_queue.json --completed $WORK/completed.json \
  --out-plan $WORK/degrade_plan.json --report $WORK/degradation_report.json
python3 $SKILL/scripts/budget_ledger.py append --ledger $WORK/ledger.jsonl \
  --kind degrade --payload '{"trigger":"R3-degrade-threshold"}'

# 7) 运行结束：成本报告（JSON + 中文 Markdown），摘录进 result.json
python3 $SKILL/scripts/cost_report.py --ledger $WORK/ledger.jsonl \
  --out $WORK/cost_report.json --md $WORK/cost_report.md
```

## 输入输出解释

- `task_queue.json`：`items[]`，每项含 `id`、`kind`、`priority`（越大越先）、`est_cost{requests,seconds,tokens}`（可缺，缺则按 R4 用缺省成本并放宽边际）、`deps[]`、`mandatory`（由 output_contract 派生）、`covers[]`（该核验覆盖的契约字段）。
- `budget_state.json`：`budget / spent / remaining`（三维）、`events`、`ledger_head`、`below_threshold`；全部从账本重算，不缓存、不手改。
- `plan.json`：`mode`（normal / degrade）、有序 `steps[]`（含触发规则、成本、所加安全边际）、`skipped[]`（含原因）、`projected_remaining_after_plan`。
- `checkpoint.json`：`result_draft` 及其 sha256、`completed`、`pending`、`ledger_head`、`prev_chain`、`state_hash`；模式详见 `references/checkpoint_format.md`。
- `degrade_plan.json` / `degradation_report.json`：逐字段处置（fill-partial / null+uncertainty）与被放弃核验清单及后果。
- `cost_report.json` / `cost_report.md`：逐步骤花费、利用率百分比、跳过项与原因、可摘录进 result.json 的表述。

## 异常处理

- **账本损坏**：sha256 链在 `verify`、`state`、`append`、`cost_report` 中均先行校验；任何一行哈希不符即退出码 1，拒绝在断裂的链上继续。
- **预算已耗尽**：若剩余预算连「检查点 + 降级报告」的最低成本都容纳不下，`plan_schedule.py` 直接退出码 1 并说明缺口；若仅低于降级阈值，则立即产出降级计划（模式 degrade）而非硬失败。
- **任务成本未知**：缺少 `est_cost` 维度时按策略文件 `default_cost` 补齐（规则 R4），并把安全边际从 `safety_margin` 放宽到 `unknown_cost_margin`，在该步的规则标注中显式记录。
- **强制任务不可调度**：转入降级模式（规则 R5），保证交付物至少覆盖 output_contract 强制字段，而非交付缺失强制字段的"完整"结果。
- **检查点被篡改**：恢复时三重校验（草稿哈希、整体 state_hash、账本链头一致性），任一失败退出码 1，绝不静默续跑。

## 限制

本技能**只做预算调度与过程审计**，明确不做以下事项（它们属于其他技能或核验步骤本身）：

- 不做传真件取证（facsimile forensics）；
- 不做日期年表构建与一致性核验（date chronology）；
- 不做权利要求版本差异比对（claim diffing）；
- 不做实体消歧（entity resolution）；
- 不做检索式设计（retrieval query design）。

此外：成本估计依赖队列中的估计值与策略缺省值，估计偏差通过安全边际与账本实记吸收，但不能保证零偏差；token 维度的"预算"按总量记账，而评测契约中 16384 token 为单次响应上限，二者口径不同，使用时应将 token 维视为保守上界约束；脚本不访问网络、不读取 `/input` 之外的隐私路径。

## 自查方法

```bash
python3 /skills/weekly-skill/scripts/selfcheck.py
```

自检以合成场景（12 项队列、预算 64 请求 / 900 秒）断言：计划第 0 步为检查点；依赖序被遵守；超支计划被拒绝（退出码 1）；阈值处触发降级且报告恰好列出被放弃项；检查点篡改被检出（退出码 1）；干净检查点恢复后待办队列完全一致；成本报告合计等于账本重算合计。全部通过时输出 `SELFCHECK OK` 并以退出码 0 结束。端到端操作示例见 `examples/example_walkthrough.md`。
