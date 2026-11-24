# 参数域判定报告 — PLAN-V1

> 域来源: `parameter_domains`；单位归一化表: `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-b-arithmetic/outputs/references/units.json`；全部判定由脚本实算。

| 参数 | 取值 | 单位 | 域 | 换算后 | 判定 | 说明 |
|---|---|---|---|---|---|---|
| 培养温度 | 37 | °C | 培养温度 ∈ [35, 36, 37] | 37 | **in_domain** | 37 ∈ [35, 36, 37] ? 是 |
| 培养时间 | 2880 | min | 培养时间 ∈ [24, 72] h | 48 | **in_domain** | 24 ≤ 48 ≤ 72 ? 是 |
| 单孔加样量 | 100 | µL | 单孔加样量 ∈ [0.05, 0.2] mL | 0.100 | **in_domain** | 0.05 ≤ 0.100 ≤ 0.2 ? 是 |

## 汇总

- in_domain: 3
- out_of_domain: 0
- no_domain_found: 0
- unit_unconvertible: 0
