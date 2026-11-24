---
name: ppt-figure-veritas
description: 把论文/PDF 转成学术汇报 PPT 时保证图表资产保真——每张入 deck 的图真实存在、出处明确、种类合法（示意图绝不充当实验证据），重绘数值零漂移可核验。当任务涉及论文、PDF、学术汇报、PPT/PPTX/slides/演示且要求图表可追溯、证据可核验时触发。
---

# ppt-figure-veritas — 图表资产保真

## 核心立场

学术 PPT 的第一性问题不是排版，而是**视觉证据的真实性**：观众默认每张图都是
证据。示意图（schematic）被放进 results 页、重绘时数值悄悄漂移、截图出处不明，
这些错误一旦发生，整场汇报的可信度归零，且事后极难被发现。因此本 Skill 把
图表资产当作有出处、有种类、有核验门禁的一等公民：先收割建账，再按种类立法，
最后逐值核验，任何页面只允许引用账内的图。

## 三支柱

1. **先收割后写作**：paper.pdf 进来先跑 `fig_harvest.py` 建 figure_manifest.json
   （每张图的 id、页码、caption 原文、抽取文件路径），caption 与正文引用
   （"Fig. 2"）互相绑定。此后任何页面只允许引用 manifest 里的图 id。
2. **种类门禁**：`fig_classify.py` 按 caption 关键词与抽取方式把图分为
   schematic / data-figure / table-image / unknown；results 角色页禁止
   schematic；unknown 必须由 Agent 裁决并记入 change_records。
3. **重绘可核验**：重绘只允许来自 data.csv 或论文表格抽取的机器可读数值；
   `redraw_verify.py` 把声明数值与来源逐值比对（容差 0），漂移即 error；
   重绘图题注统一标注 "redrawn from Table X (values verified)"。

## 输入契约（与平台一致）

- `/input/case.json`：含 `case_id`、`output_contract`（result.json 必须原样覆盖
  其全部字段名，运行时读取，禁止硬编码）。
- `/input/task.md`：受众、时长（如 10 分钟）、页数上限（如 ≤8 页）、模板要求。
- `/input/` 下的科研材料：`paper.pdf`，可能有 `target-template.pptx`、起始稿
  pptx、`data.csv`。**先读真实文件，禁止凭文件名猜内容。**
- 工作区 `/app/work`；最终产物 `/app/output/`。

## 输出契约（result.json）

`output_contract` 字段以 case.json 为准；已核实的字段形态：

| 字段 | 形态 |
|---|---|
| `case_id` | 与 case.json 一致 |
| `status` | success / partial / failed；partial 必须写明缺什么、为什么 |
| `editable_source` | `{path, format:"pptx", slides:N, notes_present:bool}` |
| `export_artifact` | `{pdf, rendered:bool, previews:[png...], pages:N}`；未真实渲染则 rendered=false 且 exceptions 记 tool_missing |
| `content_map` | 每页 `{slide, role, title, claims[], figures[], table, sources:[{kind,ref,locator,quote}], notes_present, notes_time_sec}`；quote 必须逐字摘自论文 |
| `compliance_checks` | `[{check, expected, actual, pass}]`，actual 一律脚本实测 |
| `exceptions` | 材料缺失 / 无法判断 / 运行失败 / tool_missing 分别说明 |
| `uncertainties` | 附加：未裁决的 unknown 图、开放警告等 |
| `change_records` | `[{version, slide, change, reason, rollback}]` |

固定执行的 compliance_checks：slide_count、export_page_match、placeholder_free、
evidence_coverage、notes_coverage、figures_in_manifest、redraw_value_drift、
no_schematic_in_results。

## 分阶段流程

| 阶段 | 动作 | 脚本 | 产出 | 门禁 |
|---|---|---|---|---|
| 0 读输入 | 读 case.json/task.md/paper.pdf/data.csv，落盘初步理解 | — | work/notes | 无 |
| 1 收割 | 位图抽取 + caption 索引 + 引用绑定 | `fig_harvest.py paper.pdf --out-dir figs/ --manifest figure_manifest.json` | figs/、figure_manifest.json | manifest 非空；page-render 兜底已标注 |
| 2 分类 | 规则分类 + 置信度 + 依据；unknown 留裁决位 | `fig_classify.py figure_manifest.json --report classify_report.json` | classify_report.json、manifest 回写 kind | unknown 必须裁决或禁用 |
| 3 重绘 | Agent 从 data.csv 逐值抄入 spec.json，确定性重绘 | `chart_redraw.py spec.json --data data.csv --out figs/redrawn_<id>.png` | figs/redrawn_*.png | matplotlib 缺失 → honest missing，不伪造 |
| 4 核验 | 声明数值 vs CSV 逐值比对，容差 0 | `redraw_verify.py spec.json --data data.csv --report redraw_report.json` | redraw_report.json | mismatch>0 → exit 1，图禁入 deck |
| 5 绑定门禁 | deck.json 中每个图引用查 manifest、provenance、种类合法 | `fig_binding_lint.py deck.json figure_manifest.json --report binding_report.json` | binding_report.json | 任一 error → exit 1，禁止构建 |
| 6 构建 | python-pptx 构建可编辑 pptx，图下 provenance 小字，备注写图源页码 | `build_deck.py deck.json --template t.pptx --fig-dir figs/ --manifest figure_manifest.json --out presentation.pptx --report build_report.json` | presentation.pptx | 须先过阶段 5 |
| 7 汇总渲染 | soffice→PDF→pdftoppm→PNG；组装 result.json，全字段实测 | `make_result.py --case case.json --task task.md --deck deck.json --pptx presentation.pptx --manifest ... --binding-report ... --redraw-report ... --classify-report ... --render --out result.json` | result.json、PDF、previews | 契约字段齐全；渲染失败如实 tool_missing |

deck.json 是 deck 的结构源文件（Agent  authoring 产物），模式见
`fig_binding_lint.py` 与 `build_deck.py` 的 docstring；其中 `sources[].quote`
必须逐字摘自论文文本。

## 预算纪律（64 请求 / 900 秒）

| 预算段 | 用途 | 先存后优检查点 |
|---|---|---|
| 0–10 请求 | 读输入 + 跑阶段 1–2 | manifest 与 classify_report 落盘 |
| 10–25 请求 | 写 spec/deck.json + 阶段 3–5 | redraw/binding 报告落盘（此时即使中断也有完整证据链） |
| 25–40 请求 | 阶段 6–7，首版 pptx + result.json **立即落盘 /app/output** | 诚实 partial 已可交付 |
| 40–60 请求 | 增量优化：补 quote、修警告、调版式，每次改动重跑 lint+verify | 每轮重存 result.json |
| 60–64 请求 | 终检：自查清单过一遍，写 change_records | 最终 result.json 落盘 |

预算将尽：优先保证 result.json 诚实（status=partial + 缺项说明），不补花哨版式。

## 异常速查

PDF 加密 / 扫描件 / 图抽不出 / 公式为图片 / 模板占位符不足 / 字体缺失 /
页数超限 / 预算将尽：见 `references/exceptions.md` 的处置表。通用原则：
工具缺失 → `tool_missing` + 降级路径；判断不了 → unknown + 裁决记录；
跑不动 → honest partial。任何情况下禁止伪造软件状态与科学数据。

## 诚实 partial 规则

- status=partial 时必须在 exceptions 逐条写明：缺什么（材料/工具/时间）、
  为什么、已交付到哪一阶段；
- 渲染链路没跑通就 `rendered=false`，**禁止未渲染却声称渲染通过**；
- 重绘核验没过就把图撤出 deck，而不是关闭门禁；
- 所有 compliance_checks 的 actual 来自脚本实测，禁止凭空断言。

## 自查清单

1. result.json 含 case.json `output_contract` 全部原字段名 + uncertainties +
   change_records？
2. 每个 compliance_checks.actual 都能在对应报告/pptx 中复算？
3. deck 中每个图 id 都在 manifest，provenance 三值之一，results 页无 schematic？
4. 重绘图全部 mismatched=0，题注含 "values verified"？
5. content_map 的每条 quote 逐字出自论文？
6. PDF/PNG 预览是本次真实渲染的？
7. unknown 图已裁决并记入 change_records？

## 声明

本 Skill 不提交任何预制答案；全部输出来自对真实输入的真实运行。合成示例仅
用于演示调用方式，与平台评测案例无关。
