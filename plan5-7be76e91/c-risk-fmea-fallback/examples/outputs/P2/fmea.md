> 合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与流程，非正式案例结果。

# FMEA 分级台账 — 方案 P2

- 工具: fmea.py（确定性）
- 阈值来源: builtin:references/thresholds.json
- 阈值: critical if S>=5; high if S>=4 或 RPN>=60; medium if RPN>=25
- 统计: critical=0 high=2 medium=0 low=1
- 结论: **PASS**

| risk_id | S | L | D | RPN | 等级 | 有缓解 | fallback_ref | 标题 |
|---|---|---|---|---|---|---|---|---|
| P2-R2 | 3 | 4 | 5 | 60 | high | 是 | P2-F2 | 干燥气流不稳定产生针孔 |
| P2-R1 | 4 | 4 | 3 | 48 | high | 是 | P2-F1 | 刮涂放大后大面积膜厚不均 |
| P2-R3 | 2 | 2 | 3 | 12 | low | 是 | — | 墨水批次间粘度差异 |
