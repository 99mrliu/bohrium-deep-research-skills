# 预算台账规则（Budget Ledger）

总额：64 次模型请求 / 900 秒 / 16384 tokens 每响应。台账由 Agent 人工记账（脚本不消耗模型请求）。

## 1. 显式分配

| 桶 | 请求数 | 用途 | 备注 |
|---|---|---|---|
| 探查 | 1 | 一次性读 task.md、case.json、两份材料，跑 `run` 与 `status` | 用批量读压缩到 1 次 |
| 判断 | ≤58 | 逐条意见决策；撰写 decisions.json / edits.json；QC 失败后的修复迭代 | 每条子要求 1–2 次为常态 |
| 核验 | ≥3 | 读 qc_report.json；抽查锚点逐字命中；核对 result.json 契约字段 | **不可省，超支也要保** |
| 交付 | 2 | finalize 交付摘要核对 + 收尾说明 | 含部分完成的界限声明 |

## 2. 记账格式

每通过一个检查点（看到 `[DONE]` / `[SKIP]` / `GATE-STOP` / `FINALIZE-OK`），向 `/app/work/run.log` 追加一行：

```
BUDGET spent=<已用请求数> remain=<剩余> note=<刚完成的阶段>
```

同时在脑内维护「剩余 ÷ 剩余子要求」的均值；当均值 < 2 时触发降级。

## 3. 超支降级策略（按序砍）

1. **砍润色**：回复信保持脚本骨架，不做文学化改写（骨架已含逐条决定、理由、修改定位）。
2. **砍增量改进**：edits 一次成型，不再做第二轮措辞优化。
3. **保核验**：≥3 次核验请求是底线——核验缺失会直接威胁诚实 status 的正确性。
4. **保交付**：finalize 与 result.json 核对不可省；若判断桶耗尽，未处理子要求一律 `action=cannot` + `evidence_status=待核实`，如实落入 uncertainty（partial），绝不编造修改。

## 4. 与时间预算的联动

- 900 秒墙钟时间通常比 64 请求更松；若剩余时间 < 120 秒：立即跳到 `mark`（用当前判断文件），让确定性脚本完成 apply→letter→qc→finalize，再以 finalize 重算的诚实 status 收尾。
- 脚本运行本身（run/mark/qc/finalize）是确定性的、秒级完成，不占模型请求；不要因为「等脚本」浪费请求。
