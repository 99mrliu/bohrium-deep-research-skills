# 恢复摘要（digest，数字由产物重算）

- suspect_map.csv 单元格分类: alternative=13, clean=24, primary=3
- 置信分布: clean=24, low=13, medium=3
- 恢复单元格数（restoration_ledger.csv 行数）: 1
- 未恢复主要可疑单元格数: 2
- 恢复后等式复评: 通过 21，仍违反 4，无法评估 0
- cleaned.csv sha256: `ace551c18af99422624efbb7d45b3442489289b53f76784521c35d67ded3bfff`
- restoration_ledger.csv sha256: `05d331a5772135eaa7851100ea3f4e5c6caf885b04513877d2a582e6d72e6a39`

## 已恢复

| 单元格 | 行 | 列 | 旧值 | 新值 | 依据等式 | 方法 |
|---|---|---|---|---|---|---|
| R4C1 | R4 `合计` | C1 `n` | 96 | 90 | E001;E013;E018;E023 | 点候选 E001（col_sum）；整数列贴靠 |

## 未恢复（保留原值，写入不确定性）

| 单元格 | 行 | 列 | 当前值 | 原因 |
|---|---|---|---|---|
| R0C4 | R0 `A组` | C4 `responders` | 27 | 等式 E005, E006 含多个主要可疑单元格，非唯一可解 |
| R1C4 | R1 `B组` | C4 `responders` | 13 | 等式 E005, E006 含多个主要可疑单元格，非唯一可解 |

## 恢复后仍违反的等式

- E005（col_sum）`R0C4 + R1C4 + R3C4 = R4C4`：观测 48，期望 49
- E006（subtotal_sum）`R0C4 + R1C4 = R2C4`：观测 39，期望 40
- E014（percent）`R0C5 = 100 * R0C4 / R0C1`：观测 70，期望 90
- E015（percent）`R1C5 = 100 * R1C4 / R1C1`：观测 60，期望 43.333333
