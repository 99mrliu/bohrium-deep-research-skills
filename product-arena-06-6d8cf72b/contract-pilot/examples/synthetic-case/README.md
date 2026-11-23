# 合成示例说明（SYNTHETIC EXAMPLE — 非正式案例结果）

本目录为最小调用示例，所有材料均为虚构：

- `paper.txt`：虚构论文 "Bamboo-fiber composite panels" 文本导出，仅演示接口。
- `case.json`：虚构案例，合同含嵌套对象、数组、enum、联合类型与 minLength/minItems 约束。
- `task.md`：虚构任务说明。
- `run_example.sh`：端到端演示 init → 草稿（两处故意违规 + 假 success）→ validate 抓出 → 修复 → finalize success。
- `fill_demo_draft.py`：演示用草稿生成器，代替真实运行中的 Agent 撰写步骤。
- `sample-output.json`：一次本地运行的示意输出，标注为合成示例。

运行：`sh run_example.sh /tmp/cpl-demo`，产物写入外部目录。

真实运行时由 Agent 阅读真实论文并亲自撰写 result.json；本示例任何内容都不得作为正式案例答案。
