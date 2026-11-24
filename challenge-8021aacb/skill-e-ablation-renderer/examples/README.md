# 最小调用示例（合成示例，非正式案例结果）

全部输入为演示接口而构造的**合成数据**：

- `input/case.json`、`input/ms.md`：合成契约与合成稿件（含论证跳跃、结论超界等真实可判缺陷）。
- `curated_diagnosis.json`：真实运行中由 Agent 精读产出；此处预制为「Skill 一程」。
- `run_example.sh`：机械基线 → 结构图解析 → SVG/HTML 渲染 → 双程对照。
- `expected/`：真实执行输出。`structure_map.svg` 与 `report.html` 均为 UTF-8 文本，浏览器可直接打开；`gain_report.md` 展示机械基线与 Skill 一程的四指标对照（基线为内部消融，不代表平台基础 Agent）。

运行：`bash examples/run_example.sh`（依赖仅 python3）。
