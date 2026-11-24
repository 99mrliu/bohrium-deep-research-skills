# 发表汇总表的常见结构与恒等式清单

本文档是 consistency_check.py 建网等式的领域依据，也是 Agent 填写 constraints.json
时的对照表。发表汇总表（aggregate table）不是原始实验数据：它是汇总统计量的二维
排布，自带大量算术冗余。故障注入会破坏这些冗余恒等式，这正是定位故障的抓手。

## 1. 常见结构

### 1.1 边际合计（行合计 / 列合计）
- 末行（或末列）为“合计 / Total / Overall / 总计”，等于各分项之和。
- 只对**可加的**指标成立：例数 n、事件数、计数、累计量（sum）。
- 对均值、百分比、SD、中位数**不成立**——合计行的均值是加权均值，不是算术和。

### 1.2 嵌套小计
- “小计 / Subtotal”行汇总其上方连续的一个叶行块（从上一个小计/表头之后算起）。
- 合计 = 全部叶行之和（**不要把小计行再加进去**，否则重复计数）。
- 小计本身也应满足小计 = 块内叶行之和，这是一条独立等式。

### 1.3 百分比闭合
- 构成比/率列：pct = 部分 / 总体 × 100（行内等式）。
- 同一合计口径下各分项百分比之和 ≈ 100%（闭合等式，受舍入影响，容差取
  各分项舍入半宽之和）。
- 百分比列的可加性检查应转化为分子/分母列的等式，而不是直接对百分比求和。

### 1.4 mean–n–sum 三角
- 若表同时给出 n、均值、合计量：mean = sum / n（逐行成立）。
- 已知其中两个可反解第三个（受报告值舍入约束，反解分母/分子时是区间而非点）。

### 1.5 加权均值
- 合计行的均值 = Σ(组均值 × 组 n) / Σ(组 n)。
- 组 n 相等时退化为算术平均。

### 1.6 单位对偶列
- 同一指标以两种单位各给一列（如 mg 与 g、cm 与 m、×10⁹/L 与 /µL）：
  逐行满足 col_b = factor × col_a。两列互为冗余，是极强的交叉验证。

### 1.7 字典物理界
- 数据字典给出的取值范围（年龄 18–75、百分比 0–100、剂量上下限）是独立于
  算术等式的另一类约束；与算术违反交叉时置信最高。

## 2. 恒等式与容差

报告值是舍入后的值。单元格报告 d 位小数 ⇒ 舍入半宽 hw = 0.5×10⁻ᵈ。
整数计数字面量（n、事件数等，decimals=0 且角色为计数/可加列）视为精确，hw=0。

| 等式类型 | 形式 | 容差（误差传播） |
|---|---|---|
| col_sum / subtotal_sum | t = Σ xᵢ | hw(t) + Σ hw(xᵢ) + rel·|t| |
| percent | p = 100·a/b | hw(p) + 100·hw(a)/b + 100·a·hw(b)/b² + rel·|p| |
| mean_of_sum | m = s/n | hw(m) + hw(s)/n + s·hw(n)/n² + rel·|m| |
| weighted_mean | M = Σ mᵢnᵢ/Σ nᵢ | hw(M) + Σ(nᵢ·hw(mᵢ)+mᵢ·hw(nᵢ))/Σnᵢ + rel·|M| |
| unit_pair | b = f·a | hw(b) + f·hw(a) + rel·|b| |

rel 默认 1e-6（仅吸收浮点噪声），可在 constraints.json 的 tolerance.rel 覆盖。
判定：|观测 − 期望| > 容差 ⇒ VIOLATED，否则 PASS；参与单元格缺值/非数值/分母为 0
⇒ UNDEFINED（不计入违反，也不用于恢复）。

## 3. constraints.json schema

```json
{
  "version": "1",
  "tolerance": {"rel": 1e-6},
  "roles": {
    "label_column":   {"index": 0, "source": "…"},
    "n_columns":      [{"index": 1, "source": "…"}],
    "count_columns":  [{"index": 2, "source": "…"}],
    "additive_columns":[{"index": 9, "source": "…"}],
    "percent_columns": [{"index": 3, "numerator": 2, "denominator": 1, "source": "…"}],
    "mean_columns":   [{"index": 6, "source": "…"}],
    "sum_mean_pairs": [{"sum": 7, "mean": 8, "n": 1, "source": "…"}]
  },
  "bounds":     [{"column": 6, "min": 18, "max": 75, "source": "…"}],
  "unit_pairs": [{"column_a": 10, "column_b": 11, "factor": 1000.0, "source": "…"}]
}
```

规则：
- **每个条目必须带非空 source**（指向数据字典/工单的具体位置，如
  `data_dictionary.md#male_pct=male_n/n×100`），缺 source 时 consistency_check.py
  以退出码 4 拒绝运行——没有出处的约束本身就是不可靠的。
- 列索引为 0 基，与 structure.json 的 C 编号一致。
- 可加性（参与 col_sum/subtotal_sum）= n_columns ∪ count_columns ∪
  additive_columns ∪ sum_mean_pairs 的 sum 列。mean 与 percent 列永不参与求和。
- 加权均值等式使用 n_columns 的第一个作为权重列。
- 无法从字典确认的条目**不要写**；宁缺毋滥，缺了只是少用一类等式（降级），
  写错了会制造假阳性。
