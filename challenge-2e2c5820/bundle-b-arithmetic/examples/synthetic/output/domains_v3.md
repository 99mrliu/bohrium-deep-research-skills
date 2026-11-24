# 参数域判定报告 — PLAN-V3

> 域来源: `parameter_domains`；单位归一化表: `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-b-arithmetic/outputs/references/units.json`；全部判定由脚本实算。

| 参数 | 取值 | 单位 | 域 | 换算后 | 判定 | 说明 |
|---|---|---|---|---|---|---|
| 培养温度 | 36 | °C | 培养温度 ∈ [35, 36, 37] | 36 | **in_domain** | 36 ∈ [35, 36, 37] ? 是 |
| 培养时间 | 72 | h | 培养时间 ∈ [24, 72] h | 72 | **in_domain** | 24 ≤ 72 ≤ 72 ? 是 |
| 单孔加样量 | 150 | µL | 单孔加样量 ∈ [0.05, 0.2] mL | 0.150 | **in_domain** | 0.05 ≤ 0.150 ≤ 0.2 ? 是 |
| 离心转速 | 300 | g | 离心转速 ∈ [2000, 5000] rpm | — | **unit_unconvertible** | 单位 g ↔ rpm 不可自动换算，请专家复核（rpm↔g 依赖转子半径，绝不猜测） |
| 摇床转速 | 120 | rpm | — | — | **no_domain_found** |  |

## 汇总

- in_domain: 3
- out_of_domain: 0
- no_domain_found: 1
- unit_unconvertible: 1

## unverified 项（如实列出）
- 离心转速: 单位 g↔rpm 不可自动换算（locator: PLAN-V3#参数表#行4）
- 摇床转速: 未找到对应参数域（locator: PLAN-V3#参数表#行5）
