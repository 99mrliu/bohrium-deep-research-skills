# 数据字典（示例）

> 本文件为人工编造的合成示例，用于演示 dict-compiler 技能，不对应任何真实实验。

## 字段表

| 字段 | 单位 | 哨兵值 | 有效范围 | 检出限 | 说明 |
| --- | --- | --- | --- | --- | --- |
| sample_id | - | - | - | - | 样本主键，形如 S-001 |
| temperature_c | °C | -999 | [-50, 60] | - | 测量温度 |
| concentration | mg/L | -999, ND | [0, 100) | 0.01 | 目标物浓度 |
| ph | - | blank | [0, 14] | - | pH 值 |
| turbidity_ntu | NTU | NA | [0, 4000] | 见附录 B | 浊度 |

## 补充条目

- volume_ml: 单位 mL；哨兵 -999；物理界 [0, 1000]；量取样体积
- conductivity_us_cm: 单位 μS/cm；哨兵 -999；范围 0 ~ 2000 μS/cm
- remark_note: 自由文本备注，无 QC 规则
