> 合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与流程，非正式案例结果。

# 敏感性分析报告（decision-forge-qc / sensitivity.py）

- case_id: SYNTH-EXP-2026-001
- 基线首选: P_A
- 稳健性 verdict: **sensitive** — 首选在部分权重扰动下翻转，结论对权重取值敏感，交付时必须附带翻转点说明

## 基线权重与加权总分

| 维度 | 权重 |
|------|------|
| cost | 0.200000 |
| duration | 0.200000 |
| reliability | 0.400000 |
| safety | 0.200000 |

| 排名 | 方案 | 加权总分 |
|------|------|----------|
| 1 | P_A | 4.000000 |
| 2 | P_C | 3.600000 |
| 3 | P_B | 3.400000 |

## 扰动情景（每权重 ±50%，其余归一；另含等权重档）

| 情景 | 扰动维度 | 方向 | 首选 | 是否翻转 | 各方案总分 |
|------|---------|------|------|---------|-----------|
| cost_down | cost | down | P_A | 否 | P_A=4.250000; P_C=3.550000; P_B=3.200000 |
| cost_up | cost | up | P_A | 否 | P_A=3.750000; P_C=3.650000; P_B=3.600000 |
| duration_down | duration | down | P_A | 否 | P_A=4.000000; P_B=3.450000; P_C=3.425000 |
| duration_up | duration | up | P_A | 否 | P_A=4.000000; P_C=3.775000; P_B=3.350000 |
| reliability_down | reliability | down | P_C | **是** | P_C=4.133333; P_A=3.666667; P_B=3.533333 |
| reliability_up | reliability | up | P_A | 否 | P_A=4.333333; P_B=3.266667; P_C=3.066667 |
| safety_down | safety | down | P_A | 否 | P_A=4.000000; P_B=3.450000; P_C=3.425000 |
| safety_up | safety | up | P_A | 否 | P_A=4.000000; P_C=3.775000; P_B=3.350000 |
| equal_weights | equal_weights | equal | P_C | **是** | P_C=4.000000; P_A=3.750000; P_B=3.500000 |

## 翻转阈值（解析解，其余权重保持相对比例）

| 维度 | 下调翻转 | 上调翻转 |
|------|---------|---------|
| cost | （[0,1] 内无） | 阈值 0.333333 → P_B |
| duration | （[0,1] 内无） | 阈值 0.428571 → P_C |
| reliability | 阈值 0.307692 → P_C | （[0,1] 内无） |
| safety | （[0,1] 内无） | 阈值 0.428571 → P_C |

## 触发翻转的扰动

| 情景 | 维度 | 方向 | 翻转后首选 |
|------|------|------|-----------|
| reliability_down | reliability | down | P_C |
| equal_weights | equal_weights | equal | P_C |
