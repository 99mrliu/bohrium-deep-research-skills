# 最小调用示例（合成示例，非正式案例结果）

全部输入为演示接口而构造的**合成数据**：

- `input/case.json`、`input/ms.txt`：合成契约与合成综述稿件。
- `curated_diagnosis.json`：真实运行中由 Agent 按判据裁定产出；此处预制，且故意含两类违规——「重复内容」维既无 finding 也无 clearance、F006 的 action 为黑名单空话——用于演示覆盖门的拦截行为。
- `run_example.sh`：播种 → 线索扫描 → 覆盖门；覆盖门预期退出码 1，`expected/coverage_report.json` 列出全部 problems。
- `expected/`：真实执行 `run_example.sh` 的示意输出。

运行：`bash examples/run_example.sh`（依赖仅 python3）。
