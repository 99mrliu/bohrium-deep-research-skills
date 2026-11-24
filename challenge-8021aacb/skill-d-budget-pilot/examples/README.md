# 最小调用示例（合成示例，非正式案例结果）

全部输入为演示接口而构造的**合成数据**：

- `input/case.json`、`input/manuscript.md`：合成契约与占位稿件，仅驱动编排流程，不承担真实诊断。
- `run_example.sh`：演示完整过程协议——预算计划、初始化、五个阶段检查点（含一次降级打点）、第一次质量门因契约字段未填而 BLOCK、修复后第二次 PASS。
- `expected/`：真实执行输出；`audit_blocked.md` 与 `audit.md` 分别是阻断与通过两份终检报告，`plan.json` 为六阶段预算分配。

运行：`bash examples/run_example.sh`（依赖仅 python3）。
