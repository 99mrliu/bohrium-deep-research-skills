# examples 说明（合成示例，非正式案例结果）

本目录为**合成示例，非正式案例结果**。

- `synthetic-input/`：合成输入。`manuscript.md` 开头显著标注
  "本文为合成示例文本"，内植 2 个真实小问题：
  1. 摘要样本量 312 与正文 318 不一致（事实核验/事实错误）；
  2. 缺少数据可用性声明（学术规范/报告不全）。
  另含一句"本研究按目标期刊惯例报告了主要结局指标。"用于演示豁免词表。
- `findings_candidate.json`：Agent 已填写的候选清单（演示用），含 5 条：
  2 条真实问题、1 条 original_text 编造（演示降级 pending_review）、
  1 条 severity 非法值 "high"（演示 rejected 留痕）、1 条期刊惯例误报
  （演示豁免 recheck 提示）。运行示例流程时将其拷入 work 目录。
- `synthetic-output/`：真实跑通工作流后 result.json 与 review_report.md
  的拷贝。预期 adjudication 三类处置各至少一条：accepted 3、
  downgraded 1、rejected 1。
