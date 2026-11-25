# 调度规则：贪心策略、降级阈值与理由

> `plan_schedule.py` 的全部决策规则。每条规则在 `plan.json` 的对应步骤或
> 跳过条目中以其编号标注，保证每个决策可解释、可重放。

## 规则总表

| 编号 | 规则 | 行为 |
| --- | --- | --- |
| R0 | checkpoint-first | 任何计划的第 0 步恒为"诚实部分骨架"检查点写入 |
| R1 | mandatory-first | 强制任务（`mandatory=true`，由 output_contract 派生）构成最高优先层 |
| R2 | priority-cost-ratio | 同层内按 `priority / 归一化成本` 降序贪心；平手按 priority 降序、id 升序 |
| R3 | degrade-threshold | 任一维剩余量低于 `degrade_threshold` → 立即产出降级计划 |
| R4 | unknown-cost-default | 成本维度缺失 → 用 `default_cost` 补齐并以 `unknown_cost_margin` 适配 |
| R5 | mandatory-unschedulable | 存在装不进剩余预算的强制任务 → 转入降级计划而非硬失败 |
| R6 | dependency-skipped | 依赖被跳过（或依赖未知）的任务连带跳过并注明原因 |
| R7 | dependency-order | 只有全部依赖均已调度的任务才进入候选集 |

## 归一化成本与打分

```
norm_cost(item) = requests/64 + seconds/900 + tokens/16384    （三维归一化求和）
score(item)     = priority / max(norm_cost, ε)                 （ε = 1e-9）
```

理由：三维预算量纲不同，归一化后求和等价于"该任务消耗的总预算份额"；用优先级除以
份额，得到"单位预算份额换来的优先级"，即性价比。强制层先行（R1）保证契约底线，
性价比排序（R2）保证非强制任务的预算效率。

## 贪心循环（确定性）

1. 传播 R6：依赖已被跳过的任务标记跳过（原因中写明依赖 id）。
2. 候选集 = 未调度、未跳过、依赖全部满足（R7）。
3. 按 `(强制层, -score, -priority, id)` 排序；从队首起取第一个通过适配检查
   （`cost × margin ≤ remaining`）的任务调度之；未通过者标记 `budget-insufficient`
   并尝试下一个。
4. 一轮无人能调度则终止。
5. 终止后若存在被跳过的强制任务 → R5：整盘切换为降级计划
   （第 0 步检查点 + 第 1 步降级写入），不交付缺强制字段的"正常"结果。

确定性保证：排序键全序（id 升序兜底），输入相同则输出相同（时间戳除外）。

## 降级语义（R3 / R5）

降级计划 = 骨架检查点 + 降级写入两步。降级写入的语义由 `degrade_plan.py` 落实：

- output_contract **强制字段**：以已核验证据尽力填写（fill-partial），证据不足处
  在字段内如实标注；
- **非强制字段**：一律置 null，并为每个字段登记一条 uncertainty；
- 产出 `degradation_report.json`：逐项列出被放弃的核验、原因（剩余预算快照）、
  后果（波及的契约字段），并汇总 null 字段与部分填写字段。

理由：预算不足时最大的风险是"静默完整"——表面上字段齐全、实际未经核验。显式降级
把信息缺口变成可审计的一等公民。

## 硬失败条件

剩余预算连 `checkpoint_cost + degrade_cost` 都容纳不下时，调度器拒绝产出任何计划
（退出码 1）。此时唯一合法动作是：把既有的最后一次检查点作为交付物，并在
result.json 中以 `status=failed/partial` 如实说明。
