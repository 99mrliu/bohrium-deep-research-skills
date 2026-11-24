---
name: text-fidelity-gate
description: >-
  论文逻辑与论证审查的上游输入保真门禁。当任务是审查 /input 中的科研论文（case.json + task.md + PDF/文本材料），要求在动笔审查前先证明"将要审查的文本忠实、完整、顺序正确地来自原始材料"时使用。核心立场：多数审查失败（漏检跨章节矛盾、引用对不上、定位错位）根因不在判断层，而在输入层——PDF 解析丢字、双栏串行、长文截断、扫描件无文本层。本 Skill 用 scripts/fidelity.py（纯标准库、确定性、零依赖）先抽取并签发"保真证书"（fidelity gate: pass/degraded/fail），再把全文锚定成带全局句子编号（S0001…）与字符偏移的台账，最后用 quotecheck 强制每条 finding 的 quote 是所引句子的逐字子串，从机制上堵死"凭印象引用、定位只到章节、截断仍宣称全文审查"。不适用：文字润色、查重、参考文献格式规范、原始数据重分析与统计复算。
---

# text-fidelity-gate：上游输入保真门禁

## 定位

本 Skill 的重心在**审查的上游**：不替你判断论文对错，而是保证你审查的对象是真的。三件事：

1. **保真证书**：文本从 PDF/稿件抽取后，先做完整性与可读性体检（空文本、替换字符、缺章节、截断嫌疑、串栏嫌疑、碎行），输出 `fidelity_gate ∈ {pass, degraded, fail}`。degraded/fail 时证书写明哪些部分不可信，这些部分必须进 result.json 的"未检查项"——禁止顶着截断文本宣称"完成全文审查"。
2. **句子锚点**：全文切成带 `S0001…` 编号、0 基字符偏移、所属章节的 `sentences.jsonl`。之后所有 finding 的定位一律用句子 id + 逐字 quote，评审可直接按 id 核对。
3. **逐字关卡**：交付前 `quotecheck` 校验每条 finding 的 quote 是所引句子的逐字子串，exit≠0 必须逐条修正，不得删 quote 绕过。

判断性工作（这处矛盾算不算缺陷、严重度几何）全部留给你；工具只做确定性测量与机械校验，**只产出候选与证书，不产生审查结论**。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/fidelity.py`（下文 `$FID`，用 `python3` 运行，Python ≥3.8，纯标准库）
- 参考：`/skills/weekly-skill/references/fidelity_rubric.md`（每种告警的含义、误报边界、处置表）
- 输入：`/input/case.json`、`/input/task.md`、论文材料（PDF 或文本）
- 工作区：`/app/work`；交付：`/app/output/result.json` + 审查报告
- `result.json` 必须含原 `case_id` 与 `output_contract` 的全部字段；保真证书结论要映射进去（未检查项、不确定性、provenance 中的 `paper_sha256`）

## 执行协议（按顺序；第 0 步先落骨架，任何中断都有诚实半成品）

### 第 0 步：读契约、写骨架（最先做）

1. 读 `/input/case.json`：记录 `case_id` 与 `output_contract` 全部字段名。
2. 读 `/input/task.md`：把题目检查项抄进工作笔记。
3. 立即写 `/app/output/result.json` 骨架：`case_id`、output_contract 全字段（占位 null/空数组）、`status: "in_progress"`。此后每过一关回填一次。

### 第 1 步：抽取

```bash
python3 $FID extract --input /input/<论文.pdf或.txt> --work /app/work
```

PDF 走 `pdftotext -layout`；环境无 pdftotext 时改用平台 pdf-text-tool 产出 paper.txt 再以 txt 输入本步。抽取失败（扫描件无文本层、无法解码）时 exit=3：**不要硬审**——回填 result.json 状态 `未检查/no_text_layer`，写明原因后即交付诚实 partial。

### 第 2 步：保真证书

```bash
python3 $FID certificate --work /app/work   # exit: 0 pass / 2 degraded / 3 fail
```

读 `fidelity_certificate.json`：

- `gate=fail`（空文本等）：同上，标 `未检查` 并说明。
- `gate=degraded`：逐条看 `warnings`。`abrupt_end` / `canonical_sections_missing` 非空 → 相应部分列入"未检查项"，报告中禁止出现"全文""所有章节"字样；`column_interleave_suspect` / `fragmented_lines` → 对涉及段落用渲染图（pdf-render-tool）目检阅读顺序后再审。
- `gate=pass`：进入下一步。证书仍须写进 provenance。

### 第 3 步：锚定

```bash
python3 $FID anchor --work /app/work
```

得到 `sentences.jsonl`（`id / offset / section / text`）。之后审查中引用任何原文，先记下句子 id 与该句的逐字片段。

### 第 4 步：正常执行你的审查（本 Skill 不规定判断方法）

按 task.md 检查项逐条审，每条 finding 记录 `sentence_id` 与 `quote`（从 `sentences.jsonl` 里复制，不凭记忆写）。跨章节结论只能覆盖证书判定为可信的章节。

### 第 5 步：交付前过逐字关卡

```bash
python3 $FID quotecheck --work /app/work --findings /app/work/findings.json
```

findings.json 为数组，每条至少含 `id / sentence_id / quote`。exit=4 时读 `quotecheck_problems.json` 逐条修正后重跑；**全部通过才能写入 /app/output**。

### 第 6 步：交付

`/app/output/result.json`：output_contract 全字段 + `case_id` + `status`（通过/问题/待复核/未检查分列）+ `provenance`（`paper_sha256`、gate、引擎版本）+ `uncertainty`（截断、缺章节、被引文献不可得等如实写）。另落一份人读 `report.md`。

## 预算规划（64 次模型请求 / 900 秒）

工具调用不占模型预算。第 0–3 步 ≤6 次请求；第 4 步判断是主战场；第 5–6 步 ≥4 次。gate=degraded 时不要为补全缺失章节消耗预算——缺失即未检查，如实交付更快也更对。

## 异常处理

| 情况 | 处置 |
|-|-|
| 扫描版无文本层 | extract exit=3 → `未检查/no_text_layer`，不编造审查结果 |
| 长文截断、缺章节 | certificate 标出；列入未检查项，禁止宣称全文审查 |
| 串栏/碎行告警 | 用渲染图目检对应页后再引用其句子；无法确认标待复核 |
| fidelity.py 报错 | 读 stderr，引擎总是显式报错；修输入不修引擎 |
| quotecheck 不过 | 逐条按 problems 修正；禁止删 quote 字段绕过 |

## 不适用

文字润色、查重与学术不端判定、参考文献格式规范检查、原始数据重分析与统计复算、投稿策略。本 Skill 也不替代判断：它保证你审的是真文本、引用是真原文。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：手写的合成短文故意在 Discussion 末尾截断。`sh examples/minimal/run_example.sh` 真实执行全管线：证书判 `degraded`（abrupt_end + very_short），锚定 35 句，quotecheck 放行真 quote、拦下伪造 quote（exit=4）。产物在 `examples/minimal/outputs/work/`，可目检。
