# 诚实状态机规则（status_honesty_rules）

`status` 是交付物诚实性的总开关。本文件给出 completed/partial/failed 的判定规则、
必须降级为 partial 的情形清单、以及降级路径。validate_result.py 的 V3/V4 检查是这些规则的
可执行子集——**机器能拦的由门禁拦，机器拦不了的（值的内容真假）由本规则约束模型**。

## 1. 状态定义

| 状态 | 定义 | 机器可校验部分（validate） |
|---|---|---|
| `completed` | 合同全部字段均有真实、自洽的值；无遗留 pending；无 null_with_reason | 台账无 pending/null_with_reason；result 无未解释 null |
| `partial` | 主体完成，但至少一个字段因客观限制无法（完全）填充，且限制已明确说明 | uncertainty 或 limits 非空 |
| `failed` | 无法在预算内产出有意义的交付（如输入损坏、合同不可用） | reason 非空 |
| `in_progress` | 骨架/中间态，**不是交付态** | 校验门直接 exit 3 |

## 2. completed 的充要条件

1. 台账中所有合同业务字段 `fill_state=filled`（结构性字段除外）；
2. result.json 中所有合同字段非 null；
3. 台账登记的所有 `source_artifact` 路径真实存在；
4. `uncertainty` 可以为空列表——但前提是真没有不确定性；有限快照固有的限制若存在，不许假装没有；
5. "没有内容"与"无法填充"要区分：**合法的空结果用空容器表示并记 filled**
   （例如无冲突时 `conflict_resolutions: []`），不算 null_with_reason。

## 3. 必须降级为 partial 的情形（满足任一即降级）

1. 任一合同字段为 `null_with_reason`（如有限快照缺全文，无法核对全文排除原因）；
2. 任一字段的值不完整但有交付意义（如 9 篇题录只完成 7 篇的逐篇理由）；
3. 去重/冲突调解依赖的输入夹具存在歧义，模型做了选择但无法核验组织方预期；
4. 预算（64 请求 / 900 秒）耗尽导致部分步骤被跳过；
5. 合同探测走了 `runtime_minimum_fallback` 回退、且无法人工确认业务合同是否完整；
6. 任何"拿不准该算 completed 还是 partial"的情况——**一律 partial**。

## 4. failed 的判定与底线

- 输入完全不可用（case.json 损坏且 task.md 无合同信息）、合同不可用（case_id 探测失败）、
  或骨架之后立刻被杀导致全字段 pending：定 `failed`，`reason` 写清客观原因；
- failed 也必须交付骨架 result.json 本身——**failed 是诚实状态，不是零交付**；
- 禁止把"工作没做完"包装成 completed；禁止为保 completed 而删除合同字段（V2 会拦截）；
- 禁止伪造人工复核、伪造外部检索结果来提升状态等级。

## 5. 降级路径

```
completed 候选
  │ 发现任一 §3 情形
  ▼
partial：null_with_reason 字段补 reason → uncertainty/limits 写清限制 → 重新 validate
  │ 连主体交付都无法成立（如输入不可用）
  ▼
failed：保留骨架与已完成部分 → reason 非空 → uncertainty 记录现场 → validate 放行
```

每次状态变更都是一次 `fill_ledger.py mark --field status --value '"<state>"'`，
自动写入 `change_records`，保证评测器可回放"状态是怎么定下来的"。
