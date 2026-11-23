# 合成示例说明（SYNTHETIC EXAMPLE — 非正式案例结果）

本目录为最小调用示例，所有材料均为虚构：

- `paper.txt`：虚构论文 "Micro-inverter versus string inverter" 文本导出，仅演示接口。
- `case.json`：虚构案例，含三个问题；q3 故意设计为未报告问题（衰减率），演示 not_reported 裁定。
- `task.md`：虚构任务说明。
- `run_example.sh`：端到端演示（窗口化 → 问题台账 → 演示检索 → 填演示裁定 → 校验装配）。
- `fill_demo_verdicts.py`：演示用固定裁定填写器，代替真实运行中 Agent 的双侧检索与撰写。
- `sample-output.json`：一次本地运行的示意输出，标注为合成示例。

运行：`sh run_example.sh /tmp/eva-demo`，产物写入外部目录。

真实运行时由 Agent 阅读真实论文并亲自完成检索与裁定；本示例任何内容都不得作为正式案例答案。
