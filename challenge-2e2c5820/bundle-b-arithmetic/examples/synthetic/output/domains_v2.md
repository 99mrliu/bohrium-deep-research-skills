# 参数域判定报告 — PLAN-V2

> 域来源: `parameter_domains`；单位归一化表: `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-b-arithmetic/outputs/references/units.json`；全部判定由脚本实算。

| 参数 | 取值 | 单位 | 域 | 换算后 | 判定 | 说明 |
|---|---|---|---|---|---|---|
| 培养温度 | 37.5 | °C | 培养温度 ∈ [35, 36, 37] | 37.5 | **out_of_domain** | 37.5 ∈ [35, 36, 37] ? 否 |
| 培养时间 | 48 | h | 培养时间 ∈ [24, 72] h | 48 | **in_domain** | 24 ≤ 48 ≤ 72 ? 是 |
| 单孔加样量 | 0.1 | mL | 单孔加样量 ∈ [0.05, 0.2] mL | 0.1 | **in_domain** | 0.05 ≤ 0.1 ≤ 0.2 ? 是 |

## 汇总

- in_domain: 2
- out_of_domain: 1
- no_domain_found: 0
- unit_unconvertible: 0
