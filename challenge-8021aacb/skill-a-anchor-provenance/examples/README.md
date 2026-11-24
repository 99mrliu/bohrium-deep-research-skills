# 最小调用示例（合成示例，非正式案例结果）

本目录演示 Skill A 的机器管线，全部为**合成数据**：

- `input/case.json`、`input/task.md`、`input/manuscript.md`：为演示接口而构造的合成输入，不是平台正式案例。
- `curated_diagnosis.json`：真实运行中由 Agent 在锚定文本上精读产出；此处预制以演示核验器行为。其中故意混入 1 条引文不逐字的 finding（`F099`），用于展示核验器如何拦截失真引文。
- `run_example.sh`：端到端运行（契约 → 抽取+QC → 核验 → 收尾）。
- `expected/`：本仓库内真实执行 `run_example.sh` 生成的示意输出。`quote_verification.json` 中 `F099` 被判 `fail`，`result.json` 为诚实 `partial`（契约字段未由模型填写，演示收尾工具的缺项标注）。

运行：`bash examples/run_example.sh`（依赖：python3；PDF/docx 分支在本合成示例不触发）。
