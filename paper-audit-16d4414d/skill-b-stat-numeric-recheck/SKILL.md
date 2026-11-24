---
name: stat-numeric-recheck
description: >-
  论文逻辑与论证审查的统计数值确定性机审引擎。当任务是审查 /input 中的科研论文（case.json + task.md + PDF/文本材料），要求发现"p 值与显著性措辞冲突、百分比与分子分母不符、置信区间不含点估计、摘要与结果数值口径不一、效应方向与数值顺序相反、数学上不可能的数值"这类可重算缺陷时使用。核心立场：凡能从文本自身重算的数值主张，不让模型凭语感判断——scripts/statscan.py（纯标准库、确定性、零依赖）先把全文切成跨行合并的句子台账、抽取全部数值提及（p 值/百分比/分数/CI/mean±SD/带单位数值/对比数对），再用 C1–C6 规则逐条重算并产出确定性候选；工具只产出候选不产生结论，每条候选必须回 sentences.jsonl 读原句确认后才升级为 finding，交付前过逐字 quote 关卡。内置定义句护栏（方法学阈值定义不误报）与相对增长语境护栏（>100% 增长率不误报）。不适用：原始数据重分析与统计复算（本题排除项）、文字润色、查重、参考文献格式。
---

# stat-numeric-recheck：统计数值确定性机审

## 定位

本 Skill 的重心在**数值层**：统计报告类缺陷是少数可以"算出来"的论文问题，也是最常被通读式审查漏掉的问题。分工：

- **工具做确定性重算**：切句（跨行合并）→ 数值提及抽取 → C1–C6 规则重算 → 候选清单（每条带句子 id、逐字 quote、重算过程、严重度提示）。
- **你做语义确认**：候选只是"这里有一处可重算的不一致"；它是不是真缺陷（例如 C5 可能撞上"两个不同量同单位"），必须读原句与上下文后决定。确认不了的标 `待复核`，不硬报。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/statscan.py`（下文 `$SS`，Python ≥3.8，纯标准库）
- 规则文档：`/skills/weekly-skill/references/checks.md`（C1–C6 的判定式、容差、误报护栏）
- 输入：`/input/case.json`、`/input/task.md`、论文材料；工作区 `/app/work`；交付 `/app/output/result.json`
- `result.json` 含原 `case_id` 与 `output_contract` 全部字段；状态区分通过/问题/待复核/未检查

## 执行协议

### 第 0 步：契约与骨架（最先做）

读 `/input/case.json`（记 `case_id` + `output_contract` 字段名）与 `/input/task.md`（抄检查项）；立即写 `/app/output/result.json` 骨架（全字段占位 + `status: in_progress`），之后每阶段回填。

### 第 1 步：文本准备

PDF 先转文本：`pdftotext -layout in.pdf /app/work/paper.txt`（无 pdftotext 用平台 pdf-text-tool）。扫描件无文本层 → 标 `未检查/no_text_layer` 交付诚实 partial。长文截断嫌疑（末尾无终止标点）→ 截断后内容不纳入数值结论，写入未检查项。

### 第 2 步：扫描与重算

```bash
python3 $SS scan --input /app/work/paper.txt --work /app/work
python3 $SS check --work /app/work
```

`candidates.json`：每条候选含 `rule / sentence_id / section / quote / deterministic_detail / severity_hint`。零候选时 exit=0 且 `candidate_count=0`——"数值重算未发现不一致"本身是有效结果，写入报告的"通过项"，不要硬凑问题。

### 第 3 步：逐条确认（主战场）

对每条候选回到 `sentences.jsonl` 读原句与前后句：

1. **是不是同一个量？**（C5 常见误报：摘要与结果都出现 "cm" 但指不同测量。）
2. **是不是定义句/转述？**（引擎已有护栏，但语境千变万别；确认是作者的结果陈述再升级。）
3. **严重度**：`severity_hint` 只是起点；按是否影响主结论、是否可修正、是否影响可复现性三维定级并写明依据。
4. 确认后写入 `/app/work/findings.json`（数组；每条至少 `id / sentence_id / quote / category / severity / evidence / revision`）。revision 要落到操作：改哪个数、改哪句措辞、补哪个统计量。

### 第 4 步：逐字关卡与交付

```bash
python3 $SS verify --work /app/work --findings /app/work/findings.json
```

exit=4 逐条修正重跑，不得绕过。通过后回填 `/app/output/result.json` 与 `report.md`：每条问题带句子 id + 逐字 quote + 重算过程 + 严重度 + 可执行修改建议；`provenance` 记录 paper.txt 来源与候选/确认条数；`uncertainty` 写明无法确认项。

## 预算规划（64 请求 / 900 秒）

工具不占模型预算。第 0–2 步 ≤6 次；第 3 步按候选数均分（候选 >30 条时优先 results/abstract 的 C1/C2/C4）；第 4 步 ≥4 次。每确认一批就增量保存 findings.json。

## 异常处理

| 情况 | 处置 |
|-|-|
| 无文本层 | `未检查/no_text_layer`，不编造 |
| 文本截断 | 截断点之后不做数值结论，列入未检查项 |
| 零候选 | 如实报告"重算未发现不一致"，列入通过项 |
| 候选疑似误报 | 读原句仲裁；确认误报则在报告中说明排除理由（这是增益证据） |
| statscan 报错 | 读 stderr；引擎总是显式报错，修输入不修引擎 |

## 不适用

原始数据重分析与统计复算（本题明确排除；本工具只做"文本内可重算"的一致性）、文字润色、查重、参考文献格式、投稿策略。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：合成短文植入六处数值缺陷（p 与显著性冲突×2、百分比与分数不符、CI 不含点估计、p>1、方向与数值相反、摘要与结果口径不一）。`sh examples/minimal/run_example.sh` 真实执行：7 条候选全部命中，verify 拦下一条非逐字 quote。产物在 `examples/minimal/outputs/work/`。
