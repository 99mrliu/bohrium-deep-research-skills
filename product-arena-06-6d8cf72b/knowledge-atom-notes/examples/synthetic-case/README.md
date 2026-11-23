# 合成示例说明（SYNTHETIC EXAMPLE — 非正式案例结果）

本目录为最小调用示例，所有材料均为虚构：

- `paper.txt`：虚构论文 "Counting Bloom Sketch" 文本导出，仅演示接口。
- `case.json` / `task.md`：虚构案例输入。
- `run_example.sh`：端到端演示（章节化 → 填演示 atoms → 术语 lint → 索引 → 装配 result.json）。
- `fill_demo_atoms.py`：演示用固定知识点填写器，代替真实运行中的 Agent 撰写步骤。
- `sample-output.json`：一次本地运行的示意输出，标注为合成示例。

运行：`sh run_example.sh /tmp/kan-demo`，产物写入外部目录。

真实运行时由 Agent 阅读真实论文并亲自撰写 atoms.json；本示例任何内容都不得作为正式案例答案。
