# 统计分析报告 — case-plants-synthetic

生成时间（UTC）：2026-11-24T16:02:24Z ｜ 状态：ok

## 1. 数据来源审计（source_audit 摘要）
- `case.json`：638 B，sha256=f366c1f81d59b172…
- `plants.csv`：677 B，sha256=8db4b568013c9eea…
- `plants.db`：8192 B，sha256=e02003f3ee54e528…
- `task.md`：747 B，sha256=db760e6baae4943e…
- CSV `plants.csv`：编码 utf-8-sig，分隔符 ','，表头=有，数据行 29，列 4
- SQLite `plants.db` 表 `plants`：29 行；numeric-in-text 列：height_cm
- 跨源一致性（plants.csv ↔ plants.db）：行数 29/29（一致），列映射 exact，比对口径 full（全量 29 行），值不一致单元格 0，结论：**consistent_with_type_coercion**
- ⚠ numeric-in-text: plants.db 表 plants 的列 ['height_cm'] 以 TEXT affinity 存储数值（numeric_fraction≥0.95），已识别；跨源比对与统计解析将按数值处理

## 2. 清洗账本与闭合律
- 闭合律：rows_raw(29) == rows_kept(27) + rows_dropped(2) → **成立**
- R1 完全重复剔除（keep-first）：剔除 2 行
- R2 缺失 report_and_exclude：{'height_cm': 2, 'notes': 1}
- R3 异常值 1.5×IQR 只标记不删除：{'height_cm': 1}
- 清洗产物哈希：cleaned_table.csv sha256=00104019aacb0240…（27 行逐行哈希已入账，可被 ledger_gate 重放核验）
- ledger_gate 自检：PASS

## 3. 描述统计
| 变量 | n | 均值 | SD | 中位数 | Q1 | Q3 | min | max | 偏度 | 单位 |
|---|---|---|---|---|---|---|---|---|---|---|
| height_cm | 25 | 25.8240 | 5.2180 | 24.0000 | 22.4000 | 28.3000 | 21.3000 | 45.8000 | 2.2360 | cm |

## 4. 假设门控与推断
分组列：**group**（选择依据：auto(score=7: 列名命中分组提示词+文本列+唯一值数=2≤10)）
### height_cm
- 路线：Mann-Whitney U（两组·非正态保守路线）（理由码 `GATE_2_MANN_WHITNEY`）
- 统计量 U=0.0000，df=None，p=<0.0001，α=0.05
- 正态性：control: n=13 p=0.4781(正态)；treatment: n=12 p=<0.0001(非正态/保守)
- 非门控参照（不作决策依据）：Student t (ungated reference, 非决策依据) = -4.9837，p=<0.0001
- 原始数据参照（未去重 n=27，仅外部对照）：Student t on RAW data（未去重，仅外部对照用，非决策依据） = -5.4209，p=<0.0001
- 效应量：Hedges g=-1.9293（bootstrap95 CI [-6.4668, -1.6241], B=2000）；rank-biserial r=1.0000
- Hodges-Lehmann 中位数差=-6.1000 95%CI [-6.4000, -5.7000]

## 5. 结果解释（草稿）
- 【height_cm】（单位：cm）采用 Mann-Whitney U（两组·非正态保守路线）（理由码 GATE_2_MANN_WHITNEY）。 组间差异在 α=0.05 水平统计显著（p=<0.0001）。 Hedges g=-1.9293（大效应）；实际意义须结合单位与领域背景判断，统计显著不代表实际重要。 结论为关联性证据，非因果证明。

## 6. 不确定性、例外与限制
- 不确定性：SQLite 存在 TEXT affinity 存数值列，已按数值解析；若原口径为字符编码需人工确认
- 限制：缺失按 report_and_exclude 处理（各变量有效 n 不同），未插补；若缺失非随机，结果可能有偏。
- 限制：异常值仅按 1.5×IQR 标记未删除（除非裁决 outlier_action=drop），重尾分布下标记率会偏高。
- 限制：跨源一致性为记录级核对，不构成对上游采集过程真实性的证明。
- 限制：推断结论为关联性证据；未控制的混杂因素不在本分析范围内。

## 7. 复现信息
```json
{
  "seed": 20240501,
  "bootstrap_B": 2000,
  "python": "3.12.14",
  "platform": "macOS-15.7.4-arm64-arm-64bit",
  "generated_utc": "2026-11-24T16:02:24Z",
  "pipeline": "pipeline_a.py (dataset-veritas-gate, stdlib-only)"
}
```
