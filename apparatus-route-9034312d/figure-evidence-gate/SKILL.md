---
name: figure-evidence-gate
description: >-
  证据门禁·实体可溯源绘图。当需要从论文PDF、数据表格等研究材料生成或修改实验装置示意图、
  步骤流程图、物料流向图、技术路线图，并要求图中每个实体/关系/步骤都有逐字原文证据、
  可审计、防幻觉时触发本技能。核心做法：先建证据台账(ledger.json)，再用门禁脚本逐条核验
  quote 是否真实存在于抽取源文本，未通过门禁的元素一律不得渲染。不在范围内：纯排版美化、
  复杂图形工程的像素级精修、无溯源要求的自由插画、统计图表的复杂拟合（那些属于其他技能）。
---

# figure-evidence-gate — 证据门禁 · 实体可溯源绘图

**核心原则：图上的每个元素都必须能回指到源材料中的一句逐字原文（quote）。门禁不过，不渲染。**

本技能的差异化在于"防幻觉可溯源"，而非布局工程或 QC 修复循环。渲染器刻意保持简单通用；
台账（ledger.json）与门禁（evidence_gate.py）才是主角。

## 总览

```
/input/case.json + /task.md
  → 抽取源文本 /app/work/sources/*.txt
  → 证据台账   /app/work/ledger.json      （每个元素带 verbatim quote）
  → 门禁核验   gate_report.json           （quote 必须逐字命中源文本）
  → 渲染       figure.svg                 （仅门禁通过后）
  → 导出       PDF/PNG + export_report.json
  → 交付       /app/output/result.json
```

所有脚本仅用 Python 3 标准库，任何失败都会写 JSON 报告而非崩溃。

## 步骤表

| 步骤 | 动作 | 命令/产物 |
|---|---|---|
| 1 | 读 `/input/case.json` 与 `/task.md`；**逐字抄下 case_id 和 output_contract 的每个字段名**（之后原样写进 result.json）；盘点 /input 材料（PDF/CSV/JSON/既有SVG） | 笔记即可；尽早写 result.json 骨架 |
| 2 | 抽取源文本：PDF 用 `pdftotext -layout in.pdf /app/work/sources/<名>.txt`（或环境提供的 pdf-text-tool）；CSV/JSON 表格直接读取并另存为文本快照；扫描件才考虑 OCR 并在 uncertainties 中声明 | `/app/work/sources/*.txt` |
| 3 | 编写证据台账 `/app/work/ledger.json`：`elements[]`，每元素 `{id, kind, label, attributes{}, connects_to[]/order, source:{file, locator, quote}}`。**quote 必须是从抽取文本中复制粘贴的逐字片段**，禁止凭记忆改写；locator = 文件+页码/节/图号。kind ∈ apparatus-unit / step / flow / stage / data-item / note。字段细节见 references/ledger-schema.md | `/app/work/ledger.json` |
| 4 | 跑门禁：`python3 scripts/evidence_gate.py /app/work/ledger.json --sources-dir /app/work/sources --report /app/work/gate_report.json`。归一化（NFKC、全角→半角、空白折叠、CJK 间空格剔除、弯引号归一）后精确匹配；失败时给出 difflib 近失提示。退出码非零即阻断 | `gate_report.json`，必须 verdict=passed |
| 5 | 门禁失败处理（三选一）：①按 near_miss 提示**修正 quote**；②**删除**该元素；③**显式豁免**：元素加 `waived:true` + `waiver_reason`（仅用于图例说明、绘图约定等非事实性注记，豁免会如实出现在最终记录中，绝不容许用豁免掩盖事实性内容）。改完回到步骤 4 | 更新 ledger.json 后重跑门禁 |
| 6 | 渲染：`python3 scripts/ledger_render.py /app/work/ledger.json --out /app/output/figure.svg`。分层从左到右布局；每种 kind 一种外形（装置=圆角矩形，步骤=矩形+序号徽章，阶段=chevron，数据项=平行四边形，流=六边形，注记=虚线框）；connects_to 画箭头；每个 `<g>` 带 `id` 与 `data-eid`，`<title>` 内含 quote，可编辑可回查 | `/app/output/figure.svg` |
| 7 | 导出：`python3 scripts/export_svg.py figure.svg --pdf /app/output/figure.pdf --png /app/output/figure.png --report /app/output/export_report.json`。回退链 cairosvg → rsvg-convert → inkscape → Chrome headless；永不抛异常，逐次记录 attempts | `export_report.json` + PDF/PNG（如可用） |
| 8 | 写 `/app/output/result.json`：`case_id` + **output_contract 全部字段逐字** + `status`(success/partial/failed) + `sources`（含 locator）+ `uncertainties` + `change_records` + 台账/SVG/导出/门禁报告路径。**尽早先写骨架，随后迭代补全**；partial 必须写明限制 | `/app/output/result.json` |

## 编辑既有图（EDIT 任务）

1. 若输入提供既有 SVG 和/或既有 ledger：加载既有 ledger 作为起点（没有则为既有图中的元素反向补建台账，quote 仍须过门禁）。
2. 只改动任务要求的元素；**对新增/修改的元素重跑门禁**（最稳妥的做法是全量重跑，脚本很快）。
3. `change_records[]` 逐条记录：`{element_id, action: added|modified|removed|kept, before, after, reason, gate_verdict}`；保留元素标 `kept` 以证明未被篡改。
4. 渲染/导出/result.json 同生成流程。result.json 的 `status` 反映编辑是否全部完成。

## 异常处理

| 异常 | 处置 |
|---|---|
| 材料缺失/无法读取 | 不编造。result.json 记 `status:"failed"` 或 partial，`uncertainties` 说明缺什么；已有材料能支撑的部分照常走门禁交付 |
| PDF 无文本层 | 用 OCR（若环境具备）并**在 uncertainties 与 sources 中明确声明 "OCR"**；否则按材料缺失处理 |
| quote 匹配失败 | 看 gate_report.json 的 `near_miss`（相似度+候选原文）：通常是抄写笔误/全半角差异，按提示复制原文修正；绝不"大概差不多"放行 |
| 门禁反复不过 | 每元素最多修 3 次；仍不过则删除该元素或（仅限非事实注记）豁免，豁免数会出现在图例与报告中 |
| 中文字体缺失致 PNG 豆腐块 | SVG 本体不受影响（文本即数据）；在 uncertainties 声明字体风险；不为此反复重渲染 |
| 导出全部失败 | 属环境问题而非内容问题：交付 SVG + export_report.json（如实记录 4 级尝试），result.json 标 partial 并说明 |
| 预算将尽（见下） | 立即冻结台账，门禁通过后渲染当前版本，result.json 标 partial 并列出未完成项 |

## 预算纪律（64 次模型请求 / 900 秒）

- **一次成型**：读材料时一次性把证据摘全，ledger 一次写完，避免逐元素往返。
- 门禁失败按 near_miss 批量修正好所有 quote 再重跑，不要改一条跑一次。
- 步骤 1 完成即写 result.json 骨架；步骤 4 通过即渲染+导出，先保底交付再求精。
- 渲染器输出确定（同输入字节一致），不需要"调参看效果"式迭代；最多重渲染 1–2 次。
- 不追求美观精修——布局工程是其他技能的事，你的交付核心是**可溯源 + 门禁通过 + 记录诚实**。

## 参考文件

- `references/ledger-schema.md` — 台账完整字段规范与示例
- `references/gate-rules.md` — 匹配/归一化规则、豁免政策、pass/fail 实例
- `examples/minimal/` — 可运行的最小合成示例（台账、真实门禁报告、真实渲染 SVG、真实导出报告）
