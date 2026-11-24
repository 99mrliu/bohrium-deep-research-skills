---
name: evidence-atlas-forge
description: 引用与事实核验的"下游渲染工程"交付协议。当任务要求对论文或科研材料做审查并交付可被他人复核的成果时使用。核心立场：审查结论只有渲染成可回查的形式才算交付——每条 finding 必须同时以（a）结构化 result.json、（b）人读报告、（c）证据卡片与页图预览三种形态存在，且渲染过程本身再做一次证据校验。机制：build_atlas.py 把 result.json + 解析页文本渲染为自包含 HTML 证据图谱（执行摘要、覆盖状态、逐条证据卡：定位串/逐字摘录/判定/严重度/复核路径），渲染时对每条 quote 再做一次逐字回查，过期证据（quote 对不上原文）的卡片打 VERIFICATION FAILED 徽标并以退出码 1 硬报警——不允许渲染通过来掩盖证据断裂；page_maps.py 为每条 finding 生成 SVG 页图，高亮摘录所在行，让复核者十秒内定位原文。纯 stdlib，无外部渲染依赖。
---

# evidence-atlas-forge：证据图谱渲染与可复核交付

## 1. 定位与核心立场

本题的第四条成败标准是"每条结论能否被他人按记录回查"。常见失败是：JSON 里写了 locator 和 quote，但复核者要自己翻 PDF 逐页找，定位串形同虚设；或者报告是模型一次性写就，引用块在转写中悄悄失真。本 Skill 把重心放在**下游渲染工程**：

1. **渲染即校验**：证据卡片不是手写 Markdown，而是由脚本从 result.json + 页文本**生成**；生成时重验 quote 逐字性，断裂的证据卡会被打标并触发退出码 1——报告的美观不能掩盖证据的断裂。
2. **页图预览**：每条 finding 配一张 SVG 页图（整页文本的版面快照，摘录行高亮），复核者不开原 PDF 也能核对位置。环境提供 pdf-render-tool 时可另附原页 PNG，SVG 页图作为无依赖的保底。
3. **三态交付**：机器（result.json）、人（review_report.html/.md）、图（SVG/PNG 预览）一致同源——都由同一份结构化结果生成，禁止三处内容各自手写。

## 2. 适用条件与不适用范围

适用：一切需要交付可复核审查报告的场景；长文档收益最大。不适用：润色、综述写作、数据建模。审查判断本身（六类问题的专业判定）由 Agent 完成，本 Skill 管交付形态与证据完整性。

## 3. 运行契约（Harbor）

- 输入 `/input/case.json`、`/input/task.md`；工作目录 `/app/work`；交付 `/app/output/`。
- `result.json` 含 `case_id` 与 case.json `output_contract`（或 `outputContract`/`outputs`）声明的全部字段（同名复制，无法填充置 `null` 并记入 uncertainties）。
- 预算 64 次模型请求 / 900 秒 / ≤16384 token 每响应。渲染与校验全在脚本里，不占模型预算；中途产物落盘可恢复；诚实 partial（partial 的报告照渲染，覆盖状态如实标）。
- 禁止编造：渲染输入必须是真实写出的 result.json 与真实解析的页文本；不允许为让卡片好看而修改 quote。

### 防御式输入解析

同常规：`case_id` 多字段回退；材料字段回退到 `/input/` 文件序；task.md 优先；材料缺失走 blocked（此时仍渲染一份 blocked 报告，说明缺失）。

## 4. 工作流程

### 阶段 0：解析（脚本）

```bash
cd /app/work
python3 <SKILL_DIR>/scripts/ingest.py <材料路径> pages.jsonl
```

### 阶段 1：六类审查（Agent，约 25–35 次请求）

按常规要点完成事实核验、引用支持、方法设计、统计报告、论证链、学术规范六类审查（各覆盖状态 checked/partial/unchecked 如实标）。每条 finding 按第 6 节 schema 写入 `/app/work/result.draft.json`；quote 必须逐字取自 pages.jsonl。审查方法与判定规则不属于本 Skill 的重心，但须遵守：区分事实错误/证据不足/规范问题/建议性意见；无法确认标 待复核。

### 阶段 2：渲染与渲染门（脚本）

```bash
python3 <SKILL_DIR>/scripts/build_atlas.py \
    --result /app/work/result.draft.json --pages pages.jsonl \
    --outdir /app/output/atlas
python3 <SKILL_DIR>/scripts/page_maps.py \
    --result /app/work/result.draft.json --pages pages.jsonl \
    --outdir /app/output/atlas/pages
```

- `build_atlas.py` 输出：`report.html`（自包含，内联 CSS：执行摘要、六类覆盖状态表、待复核清单、逐条证据卡）、`atlas_manifest.json`（每条 finding 的渲染校验结果）。任一 quote 回查失败 → 该卡打 VERIFICATION FAILED 徽标，清单计数，退出码 1。
- `page_maps.py` 输出：每条 finding 一张 `F-xx_pN.svg`（整页文本逐行排版、摘录行高亮、页眉标 finding id 与 locator）与 `index.html`。
- 渲染门不过时的处置：只允许两种修复——（a）回到 pages.jsonl 取真实文本改 quote；（b）该条降级 `待复核`（`needs_human_review=true`）。**禁止**改 pages.jsonl 迁就 quote。修复后重跑渲染门直至通过或诚实 partial。

### 阶段 3：交付（Agent，2–4 次请求）

`/app/output/` 最终布局：

```
result.json            # 由 result.draft.json 定稿（含 render_manifest 摘要）
review_report.md       # 人读版（可由 HTML 内容同步精简）
run_log.jsonl
atlas/report.html      # 证据图谱
atlas/pages/*.svg      # 页图预览
atlas/atlas_manifest.json
evidence/              # pages.jsonl 副本、外部核验记录（如有）
```

环境提供 office-renderer / pdf-render-tool 时，可追加 `atlas/report.pdf` 与原页 PNG 预览；这些增强产物失败不阻塞主交付，在 uncertainties 注明。

## 5. 异常处理

| 情况 | 处置 |
|-|-|
| 解析失败 | blocked 流程；仍渲染 blocked 报告说明原因 |
| 渲染门大面积不过 | 停止渲染修复循环，回退到逐字重取（阶段 1 纪律问题），重跑 |
| 页图高亮定位失败（quote 跨行折叠后仍找不到） | 该卡页图降级为整页快照无高亮，manifest 记 `highlight=false` |
| 外部渲染器（PDF/PNG）不可用 | SVG 保底交付；uncertainties 注明增强产物缺失 |
| result.json 更新后忘记重渲染 | 渲染门含输入哈希：manifest 记录 result 与 pages 的 SHA-256，复核者可比对交付一致性 |

## 6. result.json Schema

```json
{
  "case_id": "...", "skill": "evidence-atlas-forge",
  "status": "completed | partial | blocked",
  "coverage": {"事实核验": "checked", "引用支持": "checked", "方法设计": "checked", "统计报告": "checked", "论证链": "checked", "学术规范": "checked"},
  "findings": [{"id": "F-01", "category": "...", "issue_type": "事实错误 | 证据不足 | 规范问题 | 建议性意见",
    "severity": "critical | major | minor | advisory",
    "location": {"locator": "p.3 ¶2", "page": 3, "quote": "逐字摘录"},
    "claim": "...", "verdict": "...", "basis": "...", "suggestion": "...",
    "confidence": "high | medium | low", "recheck": "...", "needs_human_review": false}],
  "render_manifest": {"atlas": "atlas/report.html", "cards": 0, "verification_failed": 0,
                      "result_sha256": "...", "pages_sha256": "..."},
  "unchecked_items": [], "uncertainties": [],
  "artifacts": {"report_html": "atlas/report.html", "page_maps": "atlas/pages/", "log": "run_log.jsonl"}
}
```

## 7. 参考资料

- `references/deliverable_contract.md`：三态交付的一致性要求与渲染门禁语义。
- `references/severity_rubric.md`：证据卡严重度分级与视觉编码规范。
- `examples/`：**合成示例**——正常渲染 + 一份埋了过期证据的 result，演示渲染门拦截。
