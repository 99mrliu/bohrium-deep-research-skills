# 数值溯源校验报告（ledger_report.md）

- 章节文件：`/Users/liuhengshen/Desktop/bhr_product/writing09-5dir/bundles/skill-a-evidence-atlas/examples/case/draft.md`
- 数值 token 总数：9；BOUND：8；UNSOURCED：1；覆盖率：88.9%

## UNSOURCED（无法在台账定位；建议删除或标注 [待确认]）

- 行 7：`0.5` — 批大小为 32。为防止过拟合，dropout 比率设为 0.5。
  - 处置建议：删除该数值，或在正文标注 `[待确认]` 并列入人工确认项。

## BOUND（已在台账定位）

- 行 6：`0.0003` ← P003
- 行 6：`0.0001` ← P004、P019
- 行 6：`50` ← P005、P013
- 行 7：`32` ← P006、P014
- 行 11：`0.8` ← P008
- 行 11：`0.1` ← P009、P010
- 行 11：`0.1` ← P009、P010
- 行 11：`42` ← P007、P020
