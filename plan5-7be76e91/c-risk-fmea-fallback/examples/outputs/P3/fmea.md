> 合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与流程，非正式案例结果。

# FMEA 分级台账 — 方案 P3

- 工具: fmea.py（确定性）
- 阈值来源: builtin:references/thresholds.json
- 阈值: critical if S>=5; high if S>=4 或 RPN>=60; medium if RPN>=25
- 统计: critical=1 high=0 medium=1 low=0
- 结论: **PASS**

| risk_id | S | L | D | RPN | 等级 | 有缓解 | fallback_ref | 标题 |
|---|---|---|---|---|---|---|---|---|
| P3-R1 | 5 | 2 | 3 | 30 | critical | 是 | — | 高真空热蒸发腔体含铯前驱体泄漏的安全风险 |
| P3-R2 | 3 | 4 | 3 | 36 | medium | 是 | P3-F1 | 蒸发源耗材货期 8 周超出 6 周交付窗口 |

## 警告
- risks[0](P3-R1): critical 级风险 fallback_ref 为空，将由 fallback_graph.py 判定
