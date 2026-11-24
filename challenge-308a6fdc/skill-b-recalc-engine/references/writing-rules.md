# 模型写作规则（配合重算账）

## 数字落笔规则

1. **先查账，后落笔**：任何数值、误差（±）、样本量（n=）、百分比、比值，先查
   `recalc_table.md`（人读）或 `derived_values.json`（机读）与材料原文；账上没有的数不写。
2. **派生数字可誊写**：按重算值保留 2–4 位有效数字誊写（如 12.1951% → 12.2%），
   核验的舍入豁免不会误报；禁止四舍五入到改变结论方向（如 0.049 → 0.05）。
3. **百分比变化必带基线**：写"升高 12.2%"时基线均值（如对照组 4.1）也须在文中或表中出现，
   且基线数字本身也要在账上。
4. **单位照抄材料**：账上是 mM 就写 mM；换算须登记 change_log（公式 + 来源数字）。
5. **显著性语言对齐材料**：材料给出检验方式与 p 值才可写"显著"；材料只说"更高"就只写"更高"；
   本 skill 不算 p 值，稿件出现材料没有的 p 值一律判 UNSUPPORTED-PVALUE。
6. **趋势不写成因果**：写"处理组高于对照组 12.2%"，不写"处理使响应升高 12.2%"，
   除非材料明确为干预/随机对照设计。

## 修补与留痕

- 对每条 UNSUPPORTED：三选一——删除（改写为定性描述）、改写为账上数字（附重算 id）、
  标【待确认：所需数据材料未提供】。
- 每条处置在 change_log 登记：`{"number", "verdict", "action", "reason"}`。
- 对账误报（如推导链中间量）：在 change_log 声明 derivation 与公式，报告中如实保留记录。

## 交付前自检

- `verify_report.md` 中 UNSUPPORTED / UNSUPPORTED-PVALUE 计数为 0，或每条均有处置记录。
- `result.json` 含 output_contract 全部字段与 case_id 原样；`preserved_facts` 只收
  RAW/DERIVED 两类通过项；未决项进 `uncertainty`；status 如实（complete/partial）。
