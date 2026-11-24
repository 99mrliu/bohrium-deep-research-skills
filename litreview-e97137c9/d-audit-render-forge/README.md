# audit-render-forge

文献综述生成的"下游渲染工程：可复核交付物锻造"Skill：综述交付物不是一篇孤立文本，
而是一套可独立复核的审计包——每条论断句 → 证据行 → 逐字摘录 → 页锚点都能在自包含
HTML 审计报告与 CSV 证据矩阵中直接点击核对；result.json 通过手写 schema 校验后才算交付。

- 入口说明：`SKILL.md`
- 运行：`python3 scripts/run_case.py init|render|finalize …`（详见 SKILL.md 第 4 节）
- 合成示例：`python3 examples/make_example.py /tmp/arf-demo`（详见 `examples/README.md`），
  含"link_check 失败 → 自动修复 → 重跑通过"闭环演示。
- 依赖：仅 Python 3 标准库；有 `pdftotext` 时自动用于 PDF，缺失时纯文本材料仍可运行。

## 交付物一览（`/app/output/`）

| 产物 | 复核入口 |
| --- | --- |
| `audit_report.html` | 浏览器直接打开，论断→证据→摘录→锚点可点击 |
| `evidence_matrix.csv` | Excel/Numbers 直接打开（UTF-8 带 BOM） |
| `coverage_map.json` | 文档×主题覆盖矩阵 + 未覆盖文档清单 |
| `link_check_report.json` | 标记解析校验结果（ok 布尔 + 明细） |
| `validation_report.json` | result.json schema 校验结果 |
| `result.json` | 终版结构化结果（镜像 output_contract 全字段） |
