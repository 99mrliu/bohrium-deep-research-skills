# 最小调用示例（合成示例，非正式案例结果）

全部输入为演示接口而构造的**合成数据**：

- `input/case.json`、`input/ms.md`：合成契约与合成稿件（方法节后置、整段重复、结论超界）。
- `ops_valid.json`：真实运行中由 Agent 从诊断 finding 翻译；此处预制，含章节前移、删重、论断收窄、补过渡、补限制五种操作。
- `ops_bad.json`：故意含坏块引用与非逐字强删，演示校验器与模拟器的双重拒绝。
- `run_example.sh`：端到端演示；`expected/` 为真实执行输出，其中 `revised_skeleton.md` 展示改后骨架（方法已前移、重复段已删、论断已收窄）。

运行：`bash examples/run_example.sh`（依赖仅 python3）。
