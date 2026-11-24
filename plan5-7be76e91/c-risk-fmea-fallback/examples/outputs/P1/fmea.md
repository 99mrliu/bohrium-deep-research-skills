> 合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与流程，非正式案例结果。

# FMEA 分级台账 — 方案 P1

- 工具: fmea.py（确定性）
- 阈值来源: builtin:references/thresholds.json
- 阈值: critical if S>=5; high if S>=4 或 RPN>=60; medium if RPN>=25
- 统计: critical=0 high=0 medium=0 low=3
- 结论: **PASS**

| risk_id | S | L | D | RPN | 等级 | 有缓解 | fallback_ref | 标题 |
|---|---|---|---|---|---|---|---|---|
| P1-R3 | 2 | 3 | 4 | 24 | low | 是 | — | 旋涂边缘珠边效应影响有效面积 |
| P1-R1 | 2 | 3 | 3 | 18 | low | 是 | P1-F1 | 环境湿度波动导致结晶不均匀 |
| P1-R2 | 2 | 2 | 2 | 8 | low | 是 | — | 前驱体溶液老化导致成膜缺陷 |
