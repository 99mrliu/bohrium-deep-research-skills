# 计算与对账规则

## 精确数与舍入

JSON 数值以 `parse_float=Decimal`、`parse_int=Decimal` 读入，再转 `Fraction`。所有中间运算使用有理数精确计算；只有最终展示按 `ROUND_HALF_UP` 或 `ROUND_HALF_EVEN` 舍入。结果同时保存 `exact_result` 分数、`rounded_value`、`formula`、`rounding` 和 `direct_vs_calculated`。循环小数不能被伪装成精确有限小数。

## 运算定义

| operation | operands | 公式 | 输出单位 |
|---|---|---|---|
| `share` | numerator, denominator | numerator / denominator × 100 | percent |
| `ratio_percent_change` | baseline, new | (new - baseline) / baseline × 100 | percent |
| `relative_cpu_time_change` | baseline_cpu_time, candidate_cpu_time | (candidate - baseline) / baseline × 100 | percent |
| `sum_reconciliation` | parts[], total | sum(parts) - total | 输入共同单位 |
| `residual` | left, right | left - right | 输入共同单位 |

`share` 的 denominator 以及两个 change 运算的 baseline 不得为零。CPU change 为负表示候选 CPU 时间相对减少，但不自动等同于“速度提升 25%”。`sum_reconciliation` 的精确残差非零即为对账不平。`residual` 只计算差值；是否可接受必须由来源另给阈值，不能自行设容差。

## 操作数与证据绑定

普通操作数通过 `operand_evidence_ids` 绑定；parts 通过 `part_evidence_ids` 按索引等长绑定。每个 ID 必须存在，且操作数与 evidence 的 value 精确相等。引用不存在、值不一致、缺操作数、未知 null 都使当前断言 unresolved 并返回非零；不继续给该断言填数。

`operand_units` 与 `operand_kinds` 必须完整且同运算内兼容。`scope.compatible` 必须为 true，同时给出 numerator/denominator 或 baseline/new 的范围说明。脚本验证声明与证据一致性，但不能证明自然语言分母在科学上合理；审阅者仍须判断分母是否对应题意。

## 直接报告 vs 计算

- `kind: direct`：来源明确给值。必须有一个数值 evidence，断言 value/unit 与该 evidence 完全一致；没有复算公式。
- `kind: calculated`：必须由明确源操作数运行受支持运算，保留精确值与舍入值。
- `kind: qualitative`：只记录有证据的质性判断，不产生数值。

来源直接给出总值时仍可对 parts 做 `sum_reconciliation`，但 total 保持 direct，残差是 calculated。不得把舍入后的展示值当作下一轮精确输入。

## 失败与 honest partial

启动后即写 `status: partial` 的 work ledger、calculations 和 result；每条处理后更新。除零、分母混淆、单位不一致、缺操作数、evidence 缺失或对账不平会：

1. 保留之前成功的断言；
2. 当前断言写为 `pending`，记录错误、未填数值；
3. 顶层写 `status: failed` 与 uncertainty；
4. CLI 返回 2；输入/契约读取失败返回 2，内部意外错误返回 1。

任何失败都不静默补数、不把部分结果写成 complete。无断言时也不得声称量值验证完成。

## 对账优先级

先核 task 的 output_contract，再核证据定位与单位，然后精确复算，最后做展示舍入。资源限制为 64 requests / 900 秒；本脚本不发外部请求。未知数值始终保持未知。
