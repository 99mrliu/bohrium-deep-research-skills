---
name: severity-revision-compiler
description: >-
  论文逻辑与论证审查的严重度校准与修改建议编译器。当任务是审查 /input 中的科研论文（case.json + task.md + PDF/文本材料），已有一批候选 finding、需要把它们变成可交付审查报告时使用。核心立场：本题两类高频失败——严重度一律标"中"、建议写成"建议补充论证"类空话——根因在交付环节缺少形式门禁。scripts/compile_report.py（纯标准库、确定性、零依赖）强制：每条 confirmed finding 必须带三维定级依据（主结论影响/可修正性/可复现性影响）；revision 必须声明操作类型（rewrite/insert/delete/downgrade_strength/add_citation/add_data/recheck）、长度达标、不含空话词表、指名句子 id；≥4 条全部同级时全局告警防定级失真；随后按严重度×可修正性排出修复优先级队列，编译出按优先级排序的 report.md 与 result_fields.json。它不判断论文，它判断 finding 的交付形态。不适用：文字润色、查重、参考文献格式、原始数据复算。
---

# severity-revision-compiler：严重度校准与修改建议编译

## 定位

本 Skill 的重心在**交付层**：审查的判断做完了不算完——评审拿到手的必须是一份"每条问题真实、定位精确到句、严重度可解释、建议能直接执行"的报告。四道机制：

1. **形式门禁（lint）**：必填字段、枚举值、三维定级依据、revision 操作类型与长度、空话词表（"建议加强/建议补充论证/进一步完善/strengthen the argument…"）。有违规 exit=7，禁止编译。
2. **定级校准**：confirmed finding 必须有 rationale{main_conclusion_impact, fixability, reproducibility_impact}；≥4 条全部同级触发全局告警（定级失真信号）。
3. **修复优先级**：按 严重度 rank × fixability rank 排序——先改"critical 且一处可改"，让评审立刻知道先改哪一处。
4. **编译交付**：report.md（按优先级排序，每条含逐字 quote、依据、定级理由、操作型建议）+ result_fields.json（映射 output_contract）。work 目录有 sentences.jsonl 时自动加逐字 quote 关卡。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/compile_report.py`（下文 `$CR`，Python ≥3.8，纯标准库）
- 参考：`/skills/weekly-skill/references/severity_rubric.md`（定级决策树与锚例）、`references/revision_patterns.md`（六类检查项的建议写法）
- 输入：`/input/case.json`、`/input/task.md`、论文材料 + 你的 findings；工作区 `/app/work`；交付 `/app/output/`

## 执行协议

### 第 0 步：契约与骨架（最先做）

读 case.json/task.md；立即写 `/app/output/result.json` 骨架（`case_id` + output_contract 全字段占位 + `status: in_progress`），每阶段回填。

### 第 1–3 步：完成你的审查判断（本 Skill 不规定判断方法）

每条 finding 按下述 schema 写入 `/app/work/findings.json`：

```json
{"id": "F01", "sentence_id": "S0009",
 "quote": "The difference was statistically significant (p = 0.31).",
 "category": "stats_report", "type": "factual_error",
 "severity": "major", "status": "confirmed",
 "evidence": "S0011（Methods）定义阈值为 p < 0.05，与 p = 0.31 冲突。",
 "rationale": {"main_conclusion_impact": "…", "fixability": "easy_single_edit",
               "reproducibility_impact": "…"},
 "revision_op": "rewrite",
 "revision": "将 S0009 改为 'not statistically significant (p = 0.31)'，或重算后更正。"}
```

枚举：`category ∈ {fact_check, citation_support, method_design, stats_report, reasoning_chain, academic_norm}`；`type ∈ {factual_error, insufficient_evidence, norm_issue, suggestion}`；`severity ∈ {critical, major, minor, suggestion}`；`fixability ∈ {easy_single_edit, moderate_rewrite, needs_new_analysis, needs_new_data}`。`status=needs_review` 的条目豁免 rationale（诚实待复核比编造依据好）。

### 第 4 步：门禁 + 优先级 + 编译

```bash
python3 $CR lint --findings /app/work/findings.json --work /app/work
python3 $CR priority --findings /app/work/findings.json
python3 $CR compile --findings /app/work/findings.json --work /app/work --out /app/output --case /input/case.json
```

lint exit=7 → 读 lint_report.json 逐条修；compile 内部会先重跑 lint 与（若有 sentences.jsonl）quote 关卡，双重违规都不会产出交付物。

### 第 5 步：并入 result.json

把 `result_fields.json` 的内容按 output_contract 字段名并入 `/app/output/result.json`；report.md 已在 /app/output。`uncertainty` 写明 needs_review 条目与原因。

## 异常处理

| 情况 | 处置 |
|-|-|
| lint 反复不过 | 逐条读 violations；空话建议按 revision_patterns.md 改写，禁止删字段绕过 |
| 全部同级告警 | 回 severity_rubric.md 决策树逐条复核；确认无误报后在报告说明定级理由 |
| findings 为空 | 不编译；result.json 写"未发现问题"并列通过项与检查范围 |
| quote 关卡失败 | quote 必须与锚定句逐字一致，修正后重跑 |

## 不适用

不替代审查判断本身；不润色论文文字；不查重；不查参考文献格式；不复算原始数据。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：findings_bad.json 在 F04 植入一条空话建议（"建议补充论证"）。`sh examples/minimal/run_example.sh` 真实执行：lint 拦下（exit=7）→ 修复后放行 → 优先级队列（critical 排首）→ 编译出 report.md 与 result_fields.json。产物在 `examples/minimal/outputs/`。
