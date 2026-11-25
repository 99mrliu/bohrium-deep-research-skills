# 水印(watermark/cursor)策略

水印是逐库的增量游标:上一轮导入"走到哪里了"。本技能根据本轮在场响应
**提议**下一水印,提案恒为 `requires_approval: true` —— 组织者本地状态
是权威数据,本技能治理它,绝不静默变更它。

## 各源游标语义

### Crossref(`/works` 深分页游标)

- 语义:`cursor` 是不透明游标串(初始为 `*`),响应 `message.next-cursor`
  给出下一页游标;`offset` 是数值偏移,可比较大小。
- 推进规则(响应在场时):
  - `cursor` ← 响应的 `message.next-cursor`(若存在);
  - `offset` ← 上一 offset + 本次 `items` 条数(无上一 offset 视为 0);
  - 两者皆无信号 → `hold`,`no_progress_signal`。
- 离线注意:材料是"当时的响应",因此提案只能推进到**该响应所代表的
  位置**,不代表"最新"。

### EuropePMC(`cursorMark` 深分页)

- 语义:`cursorMark` 是不透明游标(初始 `*`),响应 `nextCursorMark`
  给出下一页;当 `nextCursorMark` 与请求值相同时表示已到末页。
- 推进规则:`nextCursorMark` 存在且不同于现值 → `advance`,否则
  `hold`(`no_progress_signal`)。

### 出版方导出(无游标语义)

- 语义:出版方 JSON/JSONL/CSV 导出通常没有游标;若记录带 `seq`,可按
  最大 seq 作 `last_seq` 水印。
- 推进规则:响应在场且含 seq → `last_seq` ← max(seq),仅当严格大于
  现值时 `advance`;无 seq → `hold`(`no_cursor_semantics`)。

### 未知来源库

- 无推进规则 → `hold`(`no_advance_rule`)。

## 推进 / 保持(hold)规则汇总

| 情形 | 动作 | hold_reason |
| --- | --- | --- |
| 该库响应缺席 | hold | `response_absent` |
| 响应在场,有推进信号且不回退 | advance(无上一水印时为 initialize) | — |
| 响应在场,无推进信号 | hold | `no_progress_signal` / `no_cursor_semantics` |
| 提议值 < 现值(数值键) | hold | `regression_guard` |
| 未知库 | hold | `no_advance_rule` |

## 回归守卫(regression guard)

数值水印键(offset / last_seq / last_id)满足全序,**提议值不得小于
现值**:一旦出现回退(例如材料其实是更旧的一页),立即拦截为 hold 并记
`regression_guard`,同时 selfcheck 的 `watermark_non_regression` 项独立
复核。字符串游标(cursor / cursorMark)不透明、无全序,只做等值比较,
不回推大小。

## 为什么提案必须显式批准

1. **状态权威性**:import_state 是组织者的账本,技能只是对账员。自动
   推进水印会让一次错误材料(旧页、半截导出)永久污染后续所有轮次。
2. **缺席不等于无事发生**:某库响应缺席时水印 HELD,但该库记录全部
   落入 `unverifiable_withdrawal`;批准提案意味着组织者确认"本轮该库
   确实没有数据",这是业务判断,不是脚本判断。
3. **可审计**:proposed_next_state.json 带 `base_state_sha256` 与
   `diff_summary`,批准/拒绝都留下显式决定;`applied` 恒为 false,
   写回动作发生在技能之外。
