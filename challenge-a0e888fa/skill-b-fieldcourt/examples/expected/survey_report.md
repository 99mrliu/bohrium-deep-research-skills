# 字段勘测报告

- 表: `examples/measurements.csv` | 数据行: 10 | 列: 5

## 字段画像

### `sample_id`
- 非空 10；数值 0；科学计数法 0；<LOD 形 0
- 样例: W-01 | W-02 | W-03
### `metric`
- 非空 10；数值 0；科学计数法 0；<LOD 形 0
- 样例: 溶解氧 | 氨氮 | 总磷
### `value`
- 非空 8；数值 7；科学计数法 0；<LOD 形 1
- 哨兵: {"ND": 1, "-999": 1}
- 样例: 8.2 | 7900 | <0.01
### `unit`
- 非空 10；数值 0；科学计数法 0；<LOD 形 0
- 样例: mg/L | μg/L | NTU
### `n`
- 非空 10；数值 10；科学计数法 0；<LOD 形 0
- 样例: 3

## 主键候选（归一化后唯一性）

- `sample_id`: distinct=9/10 ⚠重复组 1
- `metric`: distinct=4/10 ⚠重复组 6
- `value`: distinct=9/10 ⚠重复组 1
- `unit`: distinct=3/10 ⚠重复组 7
- `n`: distinct=1/10 ⚠重复组 9

下一步：复制 decisions.template.json 为 decisions.json，对照数据字典、
单位/QC 规则与工单逐项填写 policy、missing 分类、bounds 与 source，
然后运行 adjudicate.py。

数据字典摘引（examples/dictionary.md 前 40 行）：

  # 数据字典（合成示例）
  
  | 字段 | 含义 | 约束 |
  |---|---|---|
  | sample_id | 样品编号，主键的一部分 | 形如 W-NN，大小写不敏感 |
  | metric | 指标名，主键的一部分 | 溶解氧/氨氮/总磷/浊度 |
  | value | 测量均值 | 数值或缺失码 |
  | unit | 单位 | 浓度类规范单位为 mg/L |
  | n | 重复测定次数 | 正整数 |
  
  ## 缺失码表（本案例约定）
  
  - `ND`：未检出（not_detected）
  - `<数值`：低于检出限（below_lod），保留原字面值
  - `-999`：录入缺失（entry_missing）
  - `0`：真值 0（true_zero），是有效测量值
  
  ## QC 规则（合成）
  
  - 溶解氧物理界：0–20 mg/L
  - 总磷物理界：0–5 mg/L
