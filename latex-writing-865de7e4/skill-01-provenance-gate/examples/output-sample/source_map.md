# 事实 ↔ 来源映射（source_map）

> 合成示例（synthetic example），非正式案例结果。骨架由 finalize.py 生成，「Agent 确认」列由 Agent 补全。

| 稿件位置 | 类型 | 稿件值 | 判定 | 材料锚点 | Agent 确认 |
| --- | --- | --- | --- | --- | --- |
| draft.tex:5 | percent | 94.1% | matched | data.csv:3 | 采用（task.md 第 3 条指定以 data.csv 为准） |
| draft.tex:5 | percent | 92.4% | matched | notes.md:5 | 保留为被对比口径，文中已显式说明 |
| draft.tex:5 | cite_key | wang2021cnn | matched | refs.bib:2 | 采用 |

## 已删除/已标注条目（源自初稿 coverage）

| 初稿位置 | 内容 | 初稿判定 | 处置 |
| --- | --- | --- | --- |
| draft.tex:7（初稿） | accuracy 为 93.7% | conflict | 按 task.md 第 3 条裁定采用 data.csv:3 的 94.1%，另一口径 notes.md:5 已在文中显式标注 |
| draft.tex:8（初稿） | 单次训练约 9 h | unmatched | 材料外数值，整句删除并在 LaTeX 注释说明 |
| draft.tex:9（初稿） | \cite{zhang2023unknown} | unmatched | refs.bib 无此键且无语义对应条目，移除 |
