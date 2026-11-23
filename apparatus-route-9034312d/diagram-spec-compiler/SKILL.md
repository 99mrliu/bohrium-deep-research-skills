---
name: diagram-spec-compiler
description: >-
  声明式图稿编译器：从论文 PDF、实验记录、数据表等科研材料出发，把实验装置示意图、
  步骤流程图、物料/能量/信息流向图、技术路线图编译为可编辑 SVG（并导出 PDF/PNG）。
  适用触发：需要"画装置图/流程图/路线图"、"修改已有图"且要求版式确定、图例一致、
  可继续编辑、可溯源、可导出的任务。Agent 只负责把材料整理成声明式 JSON spec，
  全部绘制由编译器完成（自动分层、端口正交布线、回流绕行、图例按构造生成、
  画布自适应、字体回退、字节级确定性重渲染，支持"改 spec → 重渲染"的保源编辑）。
  不适用范围：数据统计图表（柱状/散点等）、照片/位图处理、需要证据引用门禁或
  QC 修复循环的场景（属其他 bundle）、手绘风格插画。
---

# diagram-spec-compiler — 声明式图稿编译 · 确定性版式

核心分工：**Agent 只写 spec（JSON DSL），所有绘制由编译器完成**。
差异化能力：端口式正交布线、最长路径自动分层 + 回流检测绕行、图例与图形同源
（按构造一致）、画布 auto-fit/溢出缩放、CJK 字体探测回退链、确定性渲染
（同一 spec → 字节一致 SVG，可 diff 验证，支撑保源编辑）。

## 流水线步骤

| 步骤 | 动作 | 命令 |
|---|---|---|
| 1 | 读 `/input/case.json` 与 `/task.md`：记录 `case_id`，**逐字抄录** `output_contract` 全部字段名（稍后写入 `/app/output/result.json`）；盘点 `/input` 材料（PDF 用 `pdftotext -layout`，表格直接读） | `pdftotext -layout /input/xxx.pdf /app/work/xxx.txt`（无 pdftotext 则读原始材料并说明） |
| 2 | 在 `/app/work/` 写 `figure_spec.json`（schema 见 `references/spec-schema.md`）：kind/title/canvas/styles/nodes/edges/（roadmap 加 stages；stepflow 节点加 num）。每个节点/边带轻量 `source{locator,quote}` 溯源字段，**不做门禁** | 手写/编辑 JSON |
| 3 | 校验 spec：重复 id、未知端点、未知 flow_type、空 label、stepflow 编号连续性、roadmap 泳道引用 | `python3 scripts/check_spec.py /app/work/figure_spec.json --report /app/work/validation_report.json`（有 error 时退出码 1，必须修复后重跑） |
| 4 | 编译为可编辑 SVG（分层/端口布线/回流绕行/图例/字体链全自动） | `python3 scripts/compile_figure.py /app/work/figure_spec.json --svg /app/output/figure.svg --log /app/work/render_log.json --check-determinism` |
| 5 | 确定性验证：再编译一次并 diff（必须无输出） | `python3 scripts/compile_figure.py /app/work/figure_spec.json --svg /tmp/fig2.svg --log /tmp/log2.json && diff /app/output/figure.svg /tmp/fig2.svg` |
| 6 | 导出 PDF/PNG（回退链 cairosvg→rsvg→inkscape→Chrome headless；永不抛异常，报告如实写） | `python3 scripts/export_svg.py /app/output/figure.svg --pdf /app/output/figure.pdf --png /app/output/figure.png --report /app/work/export_report.json` |
| 7 | 写 `/app/output/result.json`：`case_id` + `output_contract` 字段逐字 + `status`/`sources`/`uncertainties`/`change_records` + 产物路径 | 见下 |

## 产物清单（/app/output/）

- `figure_spec.json`（从 /app/work 复制，**可编辑源文件**）、`figure.svg`（主交付）、
  `figure.pdf` / `figure.png`（导出生成；工具缺失时在 export_report 中如实记 unavailable）、
  `result.json`。报告类（validation/render/export）放 /app/work 并在 result.json 引用。

## result.json 要点

- 尽早先写骨架（case_id + contract 字段 + status:"partial"），完成后再补全。
- `sources`：用到的输入材料清单（文件名 + 用途）。
- `uncertainties`：材料中读不到/有歧义之处（如某管线走向材料未说明，按常理补）。
- `change_records`：**编辑类任务必填** —— 加载题目给的 spec/SVG，**只改 spec**，
  重渲染；在此记录 spec 的字段级 diff（改了哪些节点/边/样式，旧值→新值）。
- 部分完成时如实写 status:"partial" + 限制说明。

## 异常处理

| 异常 | 处理 |
|---|---|
| spec 校验报错 | 逐条修复后重跑 check_spec；不要把 error 拖进编译 |
| 材料无法解读（PDF 无文字层/格式未知） | 在 uncertainties 说明，按可读部分生成 partial 图，不虚构设备 |
| 无 CJK 字体 | 编译器只告警不失败（render_log.warnings 记录 tofu 风险）；照常交付，result.json 注明 |
| 固定画布溢出 | 编译器自动等比缩小并在 render_log.scale 记录；若 scale<0.6 考虑改 `canvas:"auto"` |
| 导出工具全缺 | export_report.json 记 unavailable；SVG 源文件仍为有效交付，result.json 注明 |
| 预算不足（64 请求/900s） | 立即落盘当前 spec+SVG（若有）+ result.json(partial)，列出剩余事项 |

## 预算纪律

- 总预算 64 次请求 / 900 秒。建议分配：读材料 ≤8，写 spec ≤12，校验-修复循环 ≤6 轮，
  编译+确定性验证 ≤4，导出 ≤3，result.json ≤4，预留 ≥10 机动。
- 不要反复微调样式刷次数；spec 一次写全，靠校验器发现问题。
- 每个脚本一步一验：失败先读报错和对应 report JSON，再决定重试。

## 参考文件

- `references/spec-schema.md` — spec 全字段文档 + 完整注释示例
- `references/layout-rules.md` — 分层/端口布线/回流/图例按构造/确定性/画布与字体策略
- `examples/minimal/` — 合成最小示例（8 节点、3 种流型、2 条回流、1 条跨层边）及全部产物
