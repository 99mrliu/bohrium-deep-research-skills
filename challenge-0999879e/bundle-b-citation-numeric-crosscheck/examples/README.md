# examples（合成示例，非正式案例结果）

- `synthetic-input/`：case.json + task.md + 合成稿件 manuscript.md（开头已显著标注
  "本文为合成示例文本"），植入 5 处问题：
  1. 摘要"准确率 94.2%" vs 结果节"91.8%"（数值不一致）；
  2. 正文引用 [5]，参考文献仅 4 条（悬空引用）；
  3. 参考文献 [2] 与 [4] 重复著录同一文献；
  4. 参考文献 [3] 未被正文引用；
  5. 结论"n=128" vs 方法"n=120"（样本量不一致）。
- `synthetic-output/`：按 SKILL.md 工作流在沙盒中**真实跑出**的 result.json 与
  review_report.md 拷贝（见端到端验证记录，5 处植入问题全部检出）。
