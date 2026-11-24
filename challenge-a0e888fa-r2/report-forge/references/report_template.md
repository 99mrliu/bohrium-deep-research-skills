# 数据质量报告：{{case_id}}

<!-- 写作要求：本报告全部数字由 fill_report.py 从 cleaned.csv / ledger.csv 重算注入，
     禁止手改任何数字；HTML 注释为写作指引，渲染时会被自动剥离。 -->

## 1. 数据概览

<!-- 写作要求：本节只陈述重算得到的客观数量，不得推断总体统计量。 -->

- 清洗后数据行数：{{total_rows}}
- 字段数：{{total_fields}}
- 缺失单元格总数：{{missing_total}}
- 整体缺失率：{{missing_rate_pct}}
- 变更记录条数：{{change_records_total}}

## 2. 问题清单

<!-- 写作要求：逐项列出发现的问题类别与数量，数量以下来两张表为准，不得增删；
     无法解释的问题必须保留并在第 5 节说明。 -->

### 2.1 按字段统计的问题条数

{{field_issue_table}}

### 2.2 按字段统计的缺失情况

{{missing_by_field_table}}

## 3. 处理动作与影响范围

<!-- 写作要求：说明每类处理动作执行了多少笔、影响哪些字段与哪些行；
     单位换算写明换算方向与依据的规则编号；非法值一律剔除不插补。 -->

{{action_summary_table}}

- 单位换算：{{unit_conversions}} 笔
- 重复行剔除：{{duplicate_groups_removed}} 组
- 非法值剔除（不插补）：{{invalid_values_dropped}} 条
- 异常标记（保留原值）：{{outliers_flagged}} 条

## 4. 图表

<!-- 写作要求：每张图必须带图表类型、选择依据（见 figure_choice.md）与图注；
     数据为空被跳过的图也必须列出原因，不得凑图。 -->

{{figures_section}}

## 5. 异常与限制说明

<!-- 写作要求：列出清洗工单中无法完成、无法解释或需人工复核之处；若无，明确写"无"。
     不得依据标签补造数据；不得插补缺失 / 非法源值。 -->

- 逐条变更记录见 ledger.csv；不确定项见 result.json 的 uncertainty 字段。
