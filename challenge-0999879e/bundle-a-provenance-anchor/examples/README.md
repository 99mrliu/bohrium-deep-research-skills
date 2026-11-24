# examples（合成示例，非正式案例结果）

本目录为**合成示例**，仅用于演示 bundle-a-provenance-anchor 的流程与产物形态，
不构成任何正式案例的审查结果。

- `synthetic-input/`：合成输入（case.json + task.md + 一篇带植入问题的虚构稿件
  manuscript.md，稿件开头已显著标注"本文为合成示例文本"）。植入问题：
  1. 摘要写甲醇产率 92%，结果节 3.1 写 89%（数值不一致，供演示锚定 finding）；
  2. 参考文献 [3] 在正文从未被引用。
- `findings_draft.example.json`：示例 finding 草稿。其中 f-003 的
  `original_text` 是**稿件中不存在的句子**，故意引错，用于演示 anchor_verify
  自动降级为 pending_review。
- `answers.example.json`：示例总体回答（含六分面登记）。
- `synthetic-output/`：用上述输入真实跑出的 result.json 与 review_report.md 拷贝。

复现方式：见 SKILL.md「分步工作流」，第 3 步用
`cp examples/findings_draft.example.json $WORK/findings_draft.json` 与
`cp examples/answers.example.json $WORK/answers.json` 代替人工撰写。
