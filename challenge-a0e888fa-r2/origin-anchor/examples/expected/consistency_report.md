# 算术自洽一致性报告（consistency_check）

- 表: `examples/trial_table.csv`
- sha256: `6c80cd8554295bbf570169c2a2e7b2f40f5ec1bd025b2a59be941c99244a738f`
- 恒等式: 共 25 条；通过 17，违反 8，无法评估 0
- 字典界检查: 违反 0 处
- 最小命中集（主要可疑单元格）: 3 个

## 逐等式裁决

| 等式 | 类型 | 表达式 | 观测 | 期望 | 容差 | 差值 | 裁决 |
|---|---|---|---|---|---|---|---|
| E001 | col_sum | `R0C1 + R1C1 + R3C1 = R4C1` | 96 | 90 | 0.00009 | 6 | VIOLATED |
| E002 | subtotal_sum | `R0C1 + R1C1 = R2C1` | 60 | 60 | 0.00006 | 0 | PASS |
| E003 | col_sum | `R0C2 + R1C2 + R3C2 = R4C2` | 51 | 51 | 0.000051 | 0 | PASS |
| E004 | subtotal_sum | `R0C2 + R1C2 = R2C2` | 33 | 33 | 0.000033 | 0 | PASS |
| E005 | col_sum | `R0C4 + R1C4 + R3C4 = R4C4` | 48 | 49 | 0.000049 | 1 | VIOLATED |
| E006 | subtotal_sum | `R0C4 + R1C4 = R2C4` | 39 | 40 | 0.00004 | 1 | VIOLATED |
| E007 | col_sum | `R0C7 + R1C7 + R3C7 = R4C7` | 10803 | 10803 | 0.010803 | 0 | PASS |
| E008 | subtotal_sum | `R0C7 + R1C7 = R2C7` | 7203 | 7203 | 0.007203 | 0 | PASS |
| E009 | percent | `R0C3 = 100 * R0C2 / R0C1` | 53.3 | 53.333333 | 0.050053 | 0.033333 | PASS |
| E010 | percent | `R1C3 = 100 * R1C2 / R1C1` | 56.7 | 56.666667 | 0.050057 | 0.033333 | PASS |
| E011 | percent | `R2C3 = 100 * R2C2 / R2C1` | 55 | 55 | 0.050055 | 0 | PASS |
| E012 | percent | `R3C3 = 100 * R3C2 / R3C1` | 60 | 60 | 0.05006 | 0 | PASS |
| E013 | percent | `R4C3 = 100 * R4C2 / R4C1` | 56.7 | 53.125 | 0.050053 | 3.575 | VIOLATED |
| E014 | percent | `R0C5 = 100 * R0C4 / R0C1` | 70 | 90 | 0.05009 | 20 | VIOLATED |
| E015 | percent | `R1C5 = 100 * R1C4 / R1C1` | 60 | 43.333333 | 0.050043 | 16.666667 | VIOLATED |
| E016 | percent | `R2C5 = 100 * R2C4 / R2C1` | 65 | 65 | 0.050065 | 0 | PASS |
| E017 | percent | `R3C5 = 100 * R3C4 / R3C1` | 30 | 30 | 0.05003 | 0 | PASS |
| E018 | percent | `R4C5 = 100 * R4C4 / R4C1` | 53.3 | 50 | 0.05005 | 3.3 | VIOLATED |
| E019 | mean_of_sum | `R0C8 = R0C7 / R0C1` | 120.5 | 120.5 | 0.050121 | 0 | PASS |
| E020 | mean_of_sum | `R1C8 = R1C7 / R1C1` | 119.6 | 119.6 | 0.05012 | 0 | PASS |
| E021 | mean_of_sum | `R2C8 = R2C7 / R2C1` | 120.1 | 120.05 | 0.05012 | 0.05 | PASS |
| E022 | mean_of_sum | `R3C8 = R3C7 / R3C1` | 120 | 120 | 0.05012 | 0 | PASS |
| E023 | mean_of_sum | `R4C8 = R4C7 / R4C1` | 120 | 112.53125 | 0.050113 | 7.46875 | VIOLATED |
| E024 | weighted_mean | `R4C6 = Σ(mean_i·n_i)/Σn_i（叶行）` | 52.8 | 52.766667 | 0.100053 | 0.033333 | PASS |
| E025 | weighted_mean | `R2C6 = Σ(mean_i·n_i)/Σn_i（块成员）` | 53.3 | 53.25 | 0.100053 | 0.05 | PASS |

## 故障定位（最小命中集）

| 单元格 | 行 | 列 | 当前值 | 参与违反等式 | 参与通过等式 | 置信 |
|---|---|---|---|---|---|---|
| R4C1 | R4 `合计` | C1 `n` | 96 | 4 | 0 | medium |
| R0C4 | R0 `A组` | C4 `responders` | 27 | 3 | 0 | medium |
| R1C4 | R1 `B组` | C4 `responders` | 13 | 3 | 0 | medium |

说明：命中集是“能解释全部违反等式的最小单元格集合”的贪心解；位于违反等式中但未被选中的单元格在 suspect_map.csv 中标为 alternative（替代解释），恢复阶段只允许处理 primary 单元格。

## 置信分级定义

- high：主要可疑单元格，同时违反算术恒等式与字典物理界。
- medium：主要可疑单元格且参与 ≥2 条违反等式；或仅违反字典界。
- low：仅参与 1 条违反等式的孤立可疑单元格，或替代解释单元格。
- clean：未参与任何违反项。
