# 重算表（recalc_table）

由 scripts/recalc.py 从原始表格确定性重算生成；所有派生量附公式与输入溯源，禁止手工改动。

## 表 `experiment_data.csv`（10 行 × 3 列）

列类型：`group`=group(缺失0)；`replicate`=identifier(缺失0)；`response`=numeric(缺失0)

### 数值列 `response` × 分组列 `group`

| 组 | n | mean | median | SD | SEM | min | max |
|---|---|---|---|---|---|---|---|
| control | 5 | 4.1 | 4.1 | 0.158114 | 0.0707107 | 3.9 | 4.3 |
| treatment | 5 | 4.6 | 4.6 | 0.158114 | 0.0707107 | 4.4 | 4.8 |

两分组派生量（基线 A = `control`，按组在数据中的首次出现顺序确定）：

| 对比 | 差值 B-A | 比值 B/A | 百分比变化 (B-A)/A×100% |
|---|---|---|---|
| treatment vs control | 0.5 | 1.12195 | 12.1951% |
