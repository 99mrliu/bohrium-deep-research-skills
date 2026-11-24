---
name: proposal-render-forge
description: |
  开题报告「下游可编辑交付」的渲染工程管线（Structured JSON Single-Source + Deterministic Multi-Format Rendering）。重心不在内容生产，而在交付形态：把开题内容组织为结构化 document JSON（七要素固定编号 1–7 + revision 修改记录），再确定性渲染出可继续编辑的 Markdown（章节编号稳定、GFM 表格、行内 [S#] 标注、文末来源清单）、纯文本 SVG 卡片预览（阶段计划节渲染横向甘特条）与自包含 HTML 预览页；修订时以 diff_ledger 产出逐节新增/删除/改写对照报告与修改记录表，满足「交付可直接继续编辑的源文件，保留章节编号、样式与图表数据，附真实渲染预览」的平台要求。
  触发：task.md 要求交付可编辑源文件/多格式预览/修订留痕，或开题报告需反复改稿且要求修改史可说明时。不触发：内容本身的研究设计裁决、引文真实性核验（本管线只管渲染与留痕，不管论断对错）。
  Trigger: deliverable-engineering for research proposals — structured JSON single source, deterministic byte-stable rendering to editable Markdown + text SVG/HTML previews (gantt for schedule), and machine-checkable revision diff ledgers. Not for: scientific-content adjudication, citation authenticity verification.
---

# 开题渲染锻造坊（Proposal Render Forge）

## 0. 定位与差异化

本 Skill 的重心是**下游可编辑交付的渲染工程**，解决两个真实失败模式：

1. **交付即死稿**：直接让模型写 Markdown，改一处就要全文重写，章节编号漂移、
   表格样式丢失、甘特图变成截图不可再编辑。本管线强制「内容只改 JSON、产物
   一律重渲染」：document JSON 是唯一事实源，Markdown/SVG/HTML 全部确定性再生成，
   章节编号由数组顺序机械生成，永不漂移。
2. **修改史说不清**：导师评审要求「说明改了什么」。`diff_ledger.py` 基于两版
   JSON 的**实际内容**逐节对照（新增/删除/改写段落 + 字数差 + 表格行级变更），
   与 revision 数组渲染的修改记录表互为印证，而非凭记忆口述。

两条铁律：渲染脚本**不读系统时钟**（确定性：同输入同输出，cmp 可验）；
schema 校验失败**拒绝渲染**（fail-fast，坏内容不进交付物）。

## 1. 运行时契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 逐字段抄录进 result.json，不凭题面猜字段名；附 PDF 材料用 `pdftotext -layout` 真实解析。 |
| 工作目录 | `/app/work`：document JSON 各版本（`doc_v1.json`、`doc_v2.json`…）、临时渲染件。 |
| 最终交付 | `/app/output/`：`result.json` + 契约字段对应产物（典型为 `proposal.md`、`preview.svg`、`preview.html`、`diff_report.md`、`revision_table.md`）。 |
| 预算 | 64 次模型请求 / 900 秒；渲染、校验、diff 全为脚本，零模型消耗。 |
| Skill 安装路径 | `/skills/weekly-skill`；路径不同时替换命令前缀。 |

## 2. 必需工作流（禁止跳步）

### 步骤 0 — 读契约 → 立即写有效 partial result.json
```
python3 /skills/weekly-skill/scripts/result_tool.py init /input/case.json /app/work/result.json
```
通读 task.md 与全部材料（PDF 先 pdftotext），把周期/经费/人员约束摘入笔记。

### 步骤 1 — 填写 document JSON（中间稿存 /app/work）
按 `references/document_schema.md` 组织内容：meta（题目/学科/周期/经费/版本/日期）
+ sections 七要素（编号 1–7，id 固定）+ sources + revision。纪律：
- 阶段计划节的表格是甘特图唯一数据源，表头必须为
  `["编号","任务","开始季度","结束季度","交付物"]`，禁止另存一份计划数据；
- 论断引用用行内 `[S#]`，`#` 必须存在于 sources（渲染器会拦截悬挂引用）；
- 指标阈值、周期、经费必须落在 case 给定条件内（本管线渲染前由 Agent 自查，
  超条件内容即使 schema 合法也不许进 JSON）。

### 步骤 2 — 渲染主交付 Markdown（可编辑）
```
python3 /skills/weekly-skill/scripts/render_markdown.py /app/work/doc_v1.json /app/output/proposal.md
```
校验失败会以退出码 2 拒绝并列出全部错误——**修 JSON 再重跑，禁止手改产物**。

### 步骤 3 — 渲染预览（SVG + HTML，均为文本）
```
python3 /skills/weekly-skill/scripts/render_preview.py /app/work/doc_v1.json /app/output/preview.svg /app/output/preview.html
```
目检 SVG：七节卡片是否齐全、甘特条起止是否与表格一致。

### 步骤 4 — 修订留痕（发生改稿时）
导师/评审意见落进 JSON 得到 doc_v2.json（revision 数组同步追加记录），然后：
```
python3 /skills/weekly-skill/scripts/render_markdown.py /app/work/doc_v2.json /app/output/proposal.md
python3 /skills/weekly-skill/scripts/render_preview.py /app/work/doc_v2.json /app/output/preview.svg /app/output/preview.html
python3 /skills/weekly-skill/scripts/diff_ledger.py diff /app/work/doc_v1.json /app/work/doc_v2.json /app/output/diff_report.md
python3 /skills/weekly-skill/scripts/diff_ledger.py revisions /app/work/doc_v2.json /app/output/revision_table.md
```

### 步骤 5 — 收尾 result.json
```
python3 /skills/weekly-skill/scripts/result_tool.py set /app/work/result.json proposal_draft /app/output/proposal.md
# ……逐契约字段 set 后：
python3 /skills/weekly-skill/scripts/result_tool.py final /app/work/result.json
cp /app/work/result.json /app/output/result.json
```
`final` 校验契约字段齐备度：缺项强制 partial 并在 uncertainty 点名；齐全才 ok。
确定性复核（建议）：连跑两次 render_markdown 后 `cmp` 字节一致再交付。

## 3. 异常处置表

| 情况 | 处置 |
|---|---|
| 材料缺失（无 PDF/无数据说明） | document JSON 相应节写「材料未提供，待补」并在 result uncertainty 点名；不编造 |
| 材料乱码/扫描件 | pdftotext 失败段落记 uncertainty，按可读部分填 JSON，照常渲染 |
| 周期过短放不下计划 | 压缩任务粒度而非虚排季度；schedule 行 `结束季度` 超 `period.quarters` 会被渲染器拦截 |
| 指标不可达 | 阈值写不进 JSON：先降指标并写明依据，再渲染；不靠渲染层兜底 |
| 预算/请求不足 | 渲染与 diff 全是脚本，最后补也 <1 分钟；优先保 proposal.md 与 result.json |
| 重复运行 | 渲染确定性保证同 JSON 同产物（cmp 可验）；result_tool 的 change_records 只追加不覆盖 |
| schema 校验失败 | 渲染器退出码 2 并列出全部错误；逐条修 JSON 后重跑，禁止绕过 |

## 4. 交付前自查清单

- [ ] proposal.md 由最新 document JSON 渲染而来（非手改），章节编号 1–7 稳定
- [ ] 双跑 render_markdown + cmp 字节一致（确定性已实证）
- [ ] preview.svg 七节卡片齐全；甘特条与阶段计划表逐行一致
- [ ] 段落 [S#] 均有 sources 条目（渲染器已拦截悬挂引用）
- [ ] 若有 v2+：diff_report.md 与 revision_table.md 均已生成且互洽
- [ ] result.json 契约字段逐字段抄录、status 诚实（缺项即 partial 并点名）

## 5. 最小示例

`examples/`：**合成示例**（城市内涝时空预测模型开题，非正式案例结果）。
`bash examples/run_example.sh` 端到端演示：契约初始化 → v1 渲染 md/svg/html →
双跑 cmp 确定性校验 → v1→v2（模拟导师两处修改）diff 报告与修改记录表 →
坏文档拦截演示 → result 收尾（含一次诚实 partial 的校验日志）。
`expected/` 全部为真实跑出的产物。
