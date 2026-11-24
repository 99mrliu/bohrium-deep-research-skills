---
name: citation-support-auditor
description: >-
  论文逻辑与论证审查的引用支持核查引擎。当任务是审查 /input 中的科研论文（case.json + task.md + PDF/文本材料），要求发现"引而未列、列而未引、引用编号断号、强主张躲在引用后面、被引文献不支持所引句子"这类引用层缺陷时使用。核心立场：引用核查分两层——文本内层（正文引用 ↔ 文献表对账）是确定性的，交给 scripts/citescan.py（纯标准库、零依赖）机判；文本外层（被引文献是否真支持那句话）是判断性的，引擎只做引用功能分类（support/contrast/method/background/mention）与强主张标记、生成逐条核查工作单，由 Agent 借助外部工具取证，取不到原文一律标待复核——本 Skill 以机制禁止凭空断言"引用不支持"。不适用：参考文献格式规范检查（本题排除项）、文字润色、查重、原始数据复算。
---

# citation-support-auditor：引用支持核查

## 定位

本 Skill 的重心在**文献层**。引用缺陷分两档，处理强度不同，混淆它们是最常见的误报来源：

1. **文本内确定性缺陷**（引擎直接定案候选）：正文引了文献表不存在的条目（cited-not-listed）、文献表列了正文从不引用的条目（listed-not-cited）、编号断号、条目重复。这些不需要读被引原文即可成立。
2. **文本外支持度问题**（引擎只立案，不定案）："被引文献不支持所引那句话"。判断它需要读被引原文。引擎生成 worksheet：每条引用的宿主句、功能分类猜测、强主张标记、文献表条目文本。你逐条处理——能获取原文（平台 browser/web 工具可用时）就取证比对；取不到就标 `待复核` 并写明"需要人工获取原文"。**禁止在未读被引原文的情况下断言"引用不支持"。**

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/citescan.py`（下文 `$CS`，Python ≥3.8，纯标准库）
- 参考：`/skills/weekly-skill/references/citation_protocol.md`（功能分类标准、外部取证流程、严重度映射）
- 输入：`/input/case.json`、`/input/task.md`、论文材料；工作区 `/app/work`；交付 `/app/output/result.json`（含原 `case_id` 与 `output_contract` 全字段）

## 执行协议

### 第 0 步：契约与骨架（最先做）

读 `/input/case.json`（`case_id` + `output_contract` 字段名）与 `/input/task.md`；立即写 `/app/output/result.json` 骨架（全字段占位 + `status: in_progress`），之后每阶段回填。

### 第 1 步：文本准备

PDF 转文本：`pdftotext -layout in.pdf /app/work/paper.txt`（无 pdftotext 用平台 pdf-text-tool）。无文本层 → `未检查/no_text_layer` 交付诚实 partial。缺 References 区：引擎会在 reconcile 写明 `reference_entries_detected=0`，该项整体标 `待复核`，禁止宣称"引用齐全"。

### 第 2 步：解析与对账

```bash
python3 $CS parse --input /app/work/paper.txt --work /app/work
python3 $CS reconcile --work /app/work
python3 $CS worksheet --work /app/work
```

- `reconcile.json`：编号引用与 author-year 引用分开对账（author-year 按"第一作者姓 + 年"归一，et al. 不造成假阴性）。
- `worksheet.json`：每条引用的宿主句、功能分类、`strong_claim_with_citation` 标记（cures/proves/establishes 类强动词 + 引用）。强主张引用是"引用不支持"的高发区，优先核查。

### 第 3 步：逐条核查（主战场）

1. 文本内缺陷（cited_not_listed 等）逐条回 `sentences.jsonl` 确认引用确实出现在正文而非被引上下文，确认后直接定案。
2. 强主张引用与关键背景引用：按 worksheet 逐条判断。有外部检索工具时查被引文献的标题/摘要与所引句的命题是否同向；**取不到原文标待复核**。
3. 区分误报：转述他人观点的句子（"X et al. showed..."）不是作者主张，不得与作者结论比对报矛盾。
4. 确认的写入 `/app/work/findings.json`（每条 `id / sentence_id / quote / category=citation_support / severity / evidence / revision`）。revision 落到操作：删哪条孤引、补哪条文献、把哪句的强度降到被引文献实际支持的水平。

### 第 4 步：逐字关卡与交付

```bash
python3 $CS verify --work /app/work --findings /app/work/findings.json
```

通过后回填 `/app/output/result.json` + `report.md`；`provenance` 记录引用/文献条目计数；`uncertainty` 列出所有待复核引用及原因。

## 预算规划（64 请求 / 900 秒）

第 0–2 步 ≤6 次；第 3 步优先强主张引用与 cited_not_listed，普通 mention 类引用抽查即可；第 4 步 ≥4 次。外部检索每条引用最多 1 次请求，失败即待复核，不纠缠。

## 异常处理

| 情况 | 处置 |
|-|-|
| 无文本层 | `未检查/no_text_layer` |
| References 区缺失/解析为空 | 引用齐全性整体待复核，禁止宣称齐全 |
| 引用格式混杂（编号+作者年混用） | 两通道分别对账，各自出结果；格式混用本身可作 norm_issue 报 minor |
| 被引文献不可得 | 标待复核并写明需要人工获取原文 |
| citescan 报错 | 读 stderr；引擎总是显式报错 |

## 不适用

参考文献格式规范检查（本题排除项，本 Skill 查的是引用逻辑不是著录格式）、文字润色、查重、原始数据复算。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：合成短文植入引而未列（编号 3 与 Wang 2021）、列而未引（编号 4）、强主张躲在引用后（"cures root rot [3]"）。`sh examples/minimal/run_example.sh` 真实执行：对账全部命中，worksheet 标出强主张引用，verify 拦下非逐字 quote。产物在 `examples/minimal/outputs/work/`。
