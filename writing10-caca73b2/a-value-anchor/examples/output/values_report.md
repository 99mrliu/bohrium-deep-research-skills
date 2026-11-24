# 数值台账报告（values_report.md）

- 材料目录: `examples/input/materials`
- 条目总数: 27
- 跳过文件: 0
- 生成器: ingest_values.py（确定性，无模型调用）

| id | kind | value | unit | error | stat | source | method | confidence | note |
|----|------|-------|------|-------|------|--------|--------|------------|------|
| V01 | stat | 1.85 | mmol/L | SD:0.22 | mean_sd | figure_caption.txt:L1 | regex | high | 均值 ± 误差（误差类型: SD）: 1.85 ± 0.22 |
| V02 | stat | 1.2 | mmol/L | SD:0.15 | mean_sd | figure_caption.txt:L1 | regex | high | 均值 ± 误差（误差类型: SD）: 1.20 ± 0.15 |
| V03 | stat | 4.3 | mmol/L | SD:0.35 | mean_sd | figure_caption.txt:L1 | regex | high | 均值 ± 误差（误差类型: SD）: 4.30 ± 0.35 |
| V04 | stat | 5.1 | mmol/L | SD:0.4 | mean_sd | figure_caption.txt:L1 | regex | high | 均值 ± 误差（误差类型: SD）: 5.10 ± 0.40 |
| V05 | stat | 10 | - | none | n | figure_caption.txt:L1 | regex | high | 样本量: n = 10 |
| V06 | table_cell | 1.2 | - | none | - | results_table.csv:R2/mean | table-parse | high |  |
| V07 | table_cell | 0.15 | - | none | SD | results_table.csv:R2/SD | table-parse | high | 该单元格本身为标准差列数值 |
| V08 | table_cell | 10.0 | - | none | - | results_table.csv:R2/n | table-parse | high |  |
| V09 | table_cell | 1.85 | - | none | - | results_table.csv:R3/mean | table-parse | high |  |
| V10 | table_cell | 0.22 | - | none | SD | results_table.csv:R3/SD | table-parse | high | 该单元格本身为标准差列数值 |
| V11 | table_cell | 10.0 | - | none | - | results_table.csv:R3/n | table-parse | high |  |
| V12 | table_cell | 5.1 | - | none | - | results_table.csv:R4/mean | table-parse | high |  |
| V13 | table_cell | 0.4 | - | none | SD | results_table.csv:R4/SD | table-parse | high | 该单元格本身为标准差列数值 |
| V14 | table_cell | 10.0 | - | none | - | results_table.csv:R4/n | table-parse | high |  |
| V15 | table_cell | 4.3 | - | none | - | results_table.csv:R5/mean | table-parse | high |  |
| V16 | table_cell | 0.35 | - | none | SD | results_table.csv:R5/SD | table-parse | high | 该单元格本身为标准差列数值 |
| V17 | table_cell | 10.0 | - | none | - | results_table.csv:R5/n | table-parse | high |  |
| V18 | stat | [0.48, 0.82] | - | CI95 | CI95 | stats_output.txt:L3 | regex | high | 95% 置信区间: 95% CI [0.48, 0.82] |
| V19 | stat | 7.95 | - | none | t | stats_output.txt:L3 | regex | high | t(df=18): t(18) = 7.95 |
| V20 | stat | 0.001 | - | none | p | stats_output.txt:L3 | regex | high | p 值（比较符 <）: p < 0.001 |
| V21 | stat | 0.65 | mmol/L | none | - | stats_output.txt:L3 | regex | high | 带单位数值: 0.65 mmol/L |
| V22 | stat | [-1.15, -0.45] | - | CI95 | CI95 | stats_output.txt:L4 | regex | high | 95% 置信区间: 95% CI [-1.15, -0.45] |
| V23 | stat | 4.77 | - | none | t | stats_output.txt:L4 | regex | high | t(df=18): t(18) = 4.77 |
| V24 | stat | 0.0002 | - | none | p | stats_output.txt:L4 | regex | high | p 值（比较符 =）: p = 0.0002 |
| V25 | stat | -0.8 | mmol/L | none | - | stats_output.txt:L4 | regex | high | 带单位数值: -0.80 mmol/L |
| V26 | stat | 10 | - | none | n | stats_output.txt:L5 | regex | high | 样本量: n = 10 |
| V27 | stat | 0.05 | - | none | alpha | stats_output.txt:L5 | regex | high | 显著性水平: alpha = 0.05 |
