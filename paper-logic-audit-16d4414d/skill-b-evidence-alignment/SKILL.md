---
name: evidence-alignment-auditor
description: >-
  论文逻辑与论证审查的证据层工作流：以"主张—证据对齐"为脊柱完成一轮可复核审查。
  当任务是审查 /input 中的科研论文（case.json + task.md + PDF/文本材料）并要求识别
  "结论超出数据""显著无统计""引用不存在的图表"这类主张与证据之间的断裂时使用。核心
  立场：最危险的逻辑问题读起来都通顺——强主张在证据层没有对应物。本 Skill 用
  scripts/evmap.py（纯标准库、确定性、零依赖）先建立证据清单（全部数值句、统计量、
  图表标题与引用、设计标签、强度词索引），再用四条机械规则（E1 结论超出数据 /
  E2 强度—设计错配 / E3 显著无统计 / E4 悬空图表引用）生成候选，由审查者逐条定案；
  交付前 verify 门禁强制 quote 逐字、证据不足条目必须写明"补什么证据才能闭环"、
  修改建议不得是空话。不适用：文字润色、查重、参考文献格式规范、原始数据重分析。
---

# evidence-alignment-auditor：每条主张都必须挂得住证据

## 定位

本 Skill 的重心在**证据层**，对应题目突破方向 2（证据支撑核查）。工作假设：
审查报告的价值 = 找到的主张—证据断裂 × 定位精度 × 建议可执行性。工具负责把
证据层结构化并生成候选；强度是否足够、候选是否成立，由你判断并写明依据。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/evmap.py`（下文 `$EV`，`python3`，≥3.8，纯标准库）
- 参考：`/skills/weekly-skill/references/evidence_rules.md`（E1–E4 规则定义、误报边界、
  强度梯度、严重度判据）
- 输入：`/input/case.json`、`/input/task.md`、论文材料（PDF 用环境 pdftotext 或平台
  pdf-text-tool 转文本）
- 工作区：`/app/work`；交付：`/app/output/result.json` + `report.md`
- `result.json` 必须含原 `case_id` 与 `output_contract` 全部字段；第 0 步先写骨架

## 执行协议

### 第 0 步：读契约、写骨架

读 case.json（记 case_id、output_contract 全字段）、task.md（检查项抄入笔记）；
立即写 `/app/output/result.json` 骨架（全字段占位 + `status: "in_progress"`）。

### 第 1 步：证据清单

```bash
python3 $EV scan --paper /app/work/paper.txt --work /app/work
```

得到 `sentences.jsonl`（S0001… 锚定）与 `evidence_map.json`：图表标题、正文图表
引用、数值句、统计量句、设计标签（pilot/可行性/横断面…）、强度词索引。
exit=3（空文本）：标 `未检查/no_text_layer` 交付诚实 partial，不硬审。

### 第 2 步：机械候选

```bash
python3 $EV candidates --work /app/work
```

`candidates.json` 输出 E1–E4 候选（定义与误报边界见 references）。**候选不是结论**：
每条都要回原文定案——成立转 finding，不成立记驳回理由（防止把有意设计误报为
缺陷），无法确认标待复核并写明缺什么。

### 第 3 步：补机器看不到的对齐判断（主战场）

候选只覆盖可机械化的断裂。你还须逐条人工对齐（每条都给 sentence_id + quote）：

- 摘要/讨论中的每个数值型主张，在结果章找到同一口径的数值句；口径不同
  （中位数 vs 均值、相对 vs 绝对）即"统计口径不一致"候选。
- 引用支持：凡"X et al. 表明/据报道 [n]"的句子，若能获取被引文献则核对支持度；
  取不到原文一律标待复核，不得凭空定案。
- 六类检查项（事实核验、引用支持、方法设计、统计报告、论证链、学术规范）以
  证据清单为底账逐类过一遍；方法与结论的因果措辞对齐优先看讨论章。

### 第 4 步：verify 门禁

```bash
python3 $EV verify --work /app/work --findings /app/work/findings.json
```

强制：quote 逐字；`type=证据不足` 必须填 `needed_evidence`（补什么证据闭环）；
suggestion 不得短于 15 字（堵"建议加强逻辑"式空话）。exit=4 逐条修正重跑，
**全过才能写 /app/output**。

### 第 5 步：交付

- `result.json`：output_contract 全字段 + case_id + findings（type ∈ {事实错误,
  证据不足, 规范问题, 建议, 待复核}；severity ∈ {critical, major, minor, info}；
  sentence_id/quote/basis/suggestion/needed_evidence）+ status（通过/问题/待复核/
  未检查分列）+ uncertainty + provenance（引擎版本、候选数、定案数、驳回数）。
- `report.md`：按严重度排序；建议落到"改哪一句、补什么证据、强度降到什么措辞"。

## 严重度判据（详表见 references）

critical：主结论级主张 E1 成立或方向与证据相反。major：关键主张 E2/E3 成立、
口径冲突。minor：E4、局部强度超标。info：改进建议。判据写进 basis，禁止一律"中"。

## 反误报规则

1. 候选是机械产物，定案必须回原文；对照组、作者自注假设、转述他人观点不得
   计为作者缺陷（详见 references 的误判边界表）。
2. E3 在理论/综述类论文上不适用——若 task.md 或文本表明非实证研究，E3 候选
   直接驳回并记理由。
3. 拿不准 → 待复核 + 说明，不凭空补结论。

## 预算规划（64 次模型请求 / 900 秒）

工具不占模型预算。第 0–2 步 ≤6 次；第 3 步按 candidate 数与主张数均分，优先
abstract/discussion 的 strong 主张；第 4–5 步 ≥4 次。预算耗尽前未定案项一律
待复核，诚实 partial 优先。

## 异常处理

| 情况 | 处置 |
|-|-|
| 扫描版无文本层 | `未检查/no_text_layer`，说明后交付 partial |
| 被引文献不可得 | 引用支持条目标待复核，注明"原文不可得" |
| 图表以图片存在无标题文本 | E4 候选降级为待复核，用 pdf-render-tool 目检再定 |
| verify exit=4 | 按 verify_report.json 逐条修正，禁止删字段绕过 |

## 不适用

文字润色、查重、参考文献格式规范、原始数据重分析与统计复算（E3 只查"有无
统计报告"，不复算 p 值）。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：试点研究合成短文，故意含
"显著无统计""pilot 设计配强断言""引用不存在的图3"。`sh examples/minimal/run_example.sh`
真实执行：scan → candidates（E1=2, E2=2, E3=1, E4=1）→ 伪造 quote 与空话建议被
verify 拦下（exit=4）→ 合规 findings 通过。产物在 `examples/minimal/outputs/work/`。
