# 清洗与对账协议（上游数据真实性）

## 原则

清洗的每一条规则都必须可复放、可撤销、可审计；**绝不静默修改数据**。
本流水线对源文件只读，所有"清洗"产出的是规则记录与标记，而不是一份
被悄悄改过的副本。

## 规则清单（按应用顺序）

1. `trim_whitespace`：每个单元格去首尾空白；不改变任何值的内容。
2. `numeric_coercion`：逐列尝试数值化。一列中全部非缺失单元格都可解析
   为浮点数才判定为数值列；失败计数逐列记录（`coercion_failures`）。
   混合列判为分类列，不做部分转换。
3. `missing_values`：缺失标记集合
   `{空, na, n/a, nan, null, none, -, --, ?, missing}`（大小写不敏感），
   逐列计数；**不插补**。
4. `duplicates`：整行完全相同的记录计数，**保留并标记**；只有任务文本
   明确要求去重时才删除，且必须记录删除数量。
5. `outliers`：每数值列按 1.5×IQR 计算上下围栏（type-7 分位数），
   越界值**仅标记不删除**；围栏值与标记数写入 `cleaning_report.json`。
6. `encoded_categorical`：整数编码的分组列（如 class=1/2/3、批次=1/2）
   改判为分类变量：进频数表、不进相关/分布面板，规则写入留痕。

## 多源对账（CSV ↔ SQLite）

同一数据同时以 CSV 快照和 SQLite 数据库提供时：

1. 行数比对；2. 列名集合比对（仅首尾空白差异时归一化并注明）；
3. 逐单元格比对（数值容差 1e-9·max(1,|a|,|b|)，其余按字符串）。
结果写入 `reconciliation.json`；任何不一致进入 `result.json` 的
`uncertainty`，并显式声明以哪个文件为准（默认 CSV 快照，因为它是
被引用最多的发布形式）。

## 留痕格式

`cleaning_report.json`：`input_rows`、每列 `{type, missing,
coerced_to_float, coercion_failures, iqr_fence_low/high,
outliers_flagged}`、`duplicate_rows`、`rules[]`（每条规则的自然语言
描述与参数）、`primary_source` 与其 SHA-256。
