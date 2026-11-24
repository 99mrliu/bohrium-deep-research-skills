# 七项审计检查的语义与失败处置

| 检查 | 通过条件 | 失败的典型原因与修复 |
|---|---|---|
| A input_freeze | 原始文件当前 sha256 与冻结清单一致 | 处理流程改写了原件 → 以 frozen 副本恢复，改为只读使用 |
| B row_reconciliation | raw 行数 = cleaned 行数 + dedup_drop 台账数 | 静默丢行/多出行；逐行对照台账补齐或恢复 |
| C_no_invented_rows | cleaned 的每个键都能在 raw 找到 | 键写错（拼接/ typo）；回到原始表核对键 |
| C_no_silent_edits | 键对齐后每个差异格都有 old/new 完全匹配的台账 | 手改了数据没记台账；把改动补记台账或回退 |
| D_dropped_rows_logged | 每个 raw 有 cleaned 无的键都有 dedup_drop | 去重没留痕；补台账（old 列存整行 JSON） |
| E_unit_inverse | 每条 unit_converted 满足 new≈old×F 且逆算成立 | 倍率写错或换算方向反；以注册表为准重算 |
| F_report_recompute | 报告行数/台账条数与现场重算一致 | 产物改了没重出报告；**以重算为准**重出报告 |
| G_workorder_coverage | 工单每条目至少一个存在的证据文件 | 漏做工单条目；补做或如实说明不做原因 |

## 跳过规则

只允许用 `--skip` 跳过确实无输入的检查（如无质量报告则跳 F）。跳过项记录在
verdict 的 `skipped` 字段，并必须同步写入 result.json 的 limitations。
把跳过多项当 PASS 交付是审计舞弊，评审按"不可核验"处理。

## 审计独立性

审计器只消费**产物与原始件**，不 import 清洗代码、不读清洗日志的"自我表扬"。
因此它能抓到的正是操作者自己最不容易看见的错误：手滑改格、漏记台账、
报告与产物不同步。修复原则是"修产物，不修审计"——审计标准不协商。
