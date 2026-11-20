# 报告完整性缺口清单（按文献类型）

`scripts/recheck.py` 按本清单逐篇生成缺口行（check_type=`completeness:*`）。
状态语义：`reported`（带 verbatim 摘录与页锚）/ `absent`（全文未检出，
是**缺口**不是过失）/ `not_applicable` / `unclear`。

文献类型判定（启发式）：全文命中 `randomized/randomised/random allocation/
placebo` → `trial`；否则 `other`。仅摘要条目同样执行，但 note 标注
"摘要口径，limited"。

## 通用项（所有文献类型）

| 键 | 检查项 | 检出信号（摘要式） |
|---|---|---|
| sample_size_justification | 样本量依据/功效 | "sample size calculation / power analysis / 80% power / powered" |
| primary_effect_with_precision | 主结局效应量与精度 | 同时采集到效应量（OR/HR/RR）与 95% CI |
| missing_data_handling | 缺失数据处理 | "missing / imputation / complete-case / ITT / per-protocol / LOCF" |
| multiplicity | 多重性控制 | "Bonferroni / Holm / Hochberg / FDR / multiplicity / multiple comparisons" |

## 试验类特有项（仅 trial，其他类型记 not_applicable）

| 键 | 检查项 | 检出信号 |
|---|---|---|
| adverse_events | 不良事件/安全性报告 | "adverse event / side effect / tolerability / safety profile / harms" |

## 使用说明

- 检出信号为正则关键词，存在漏检（词表外表述）与误检（如 "power" 用于
  他义）风险；因此 `absent` 一律措辞为"未检出相关报告（缺口）"，需要时
  由模型对 unclear 项做语境确认（计入语义裁决预算）。
- 缺口行无摘录，verify_quotes.py 对其标记 `no_quote`，不参与锚定校验。
- 清单可按 case 的 task.md 要求在运行前由模型补充条目，但补充条目必须
  以同样的"状态+摘录+页锚"格式落进 recheck 行，不得只写结论。
