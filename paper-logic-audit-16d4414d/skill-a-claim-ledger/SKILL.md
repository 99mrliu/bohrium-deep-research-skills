---
name: claim-ledger-extractor
description: >-
  论文逻辑与论证审查的论点层工作流：先把论文变成一份可逐条核查的主张清单，再做审查判断。
  当任务是审查 /input 中的科研论文（case.json + task.md + PDF/文本材料）并要求逐条给出
  问题、位置、证据与严重度时使用。核心立场：审查失败的第一根因是"审了什么"没有台账——
  主张散落在摘要、引言、结果、讨论里，作者主张、转述他人观点、假设情形混在一起，评审
  收到的报告无法逐条核对。本 Skill 用 scripts/claimledger.py（纯标准库、确定性、零依赖）
  把全文锚定成带全局句子编号（S0001…）与字符偏移的台账，机械生成主张候选清单并给出
  归因提示（author_claim? / cited_view? / hypothesis?），交付前用 lint 门禁强制：每条
  主张有合法归因与结论、quote 是所引句子的逐字子串、把转述/假设定为作者错误必须附说明。
  判断留给审查者，工具只做锚定、候选与机械校验。不适用：文字润色、查重、参考文献格式
  规范检查、原始数据重分析与统计复算。
---

# claim-ledger-extractor：先建主张清单，再下审查判断

## 定位

本 Skill 的重心在**论点层**：把"这篇论文到底主张了什么"变成一张可核查的清单，审查判断
逐条挂在清单上。它直接对应题目突破方向 1（论点与主张抽取），同时用清单结构支撑其余
检查项。三条铁律：

1. **先清单后判断**：没有进清单的主张不审；清单外的"感想"不交付。
2. **归因先于定罪**：每条主张先定 attribution（author_claim / cited_view / hypothesis /
   control_or_design），再定 verdict。转述他人观点、明确标注的假设、有意设置的对照，
   不得计为作者缺陷——这是题目点名的误读高发区。
3. **逐字引用**：每条 finding 的 quote 必须是所引句子的逐字子串，lint 不过不交付。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/claimledger.py`（下文 `$CL`，`python3` 运行，Python ≥3.8，纯标准库）
- 参考：`/skills/weekly-skill/references/claim_taxonomy.md`（归因四分法判据与 verdict 定义、严重度判据）
- 输入：`/input/case.json`、`/input/task.md`、论文材料（PDF 或文本，PDF 用环境 pdftotext 或平台 pdf-text-tool 转文本）
- 工作区：`/app/work`；交付：`/app/output/result.json` + `report.md`（人读报告）
- `result.json` 必须含原 `case_id` 与 `output_contract` 的**全部字段**；第 0 步先写骨架，任何中断都有诚实半成品

## 执行协议（按顺序）

### 第 0 步：读契约、写骨架（最先做）

1. 读 `/input/case.json`：记录 `case_id`，抄下 `output_contract` 全部字段名。
2. 读 `/input/task.md`：把题目检查项抄进工作笔记，映射到清单列。
3. 立即写 `/app/output/result.json` 骨架：case_id、output_contract 全字段（占位 null/空数组）、`status: "in_progress"`。此后每过一关回填一次。

### 第 1 步：锚定

```bash
python3 $CL anchor --paper /app/work/paper.txt --work /app/work
```

得到 `sentences.jsonl`（id / offset / section / text）与 `sections.json`。exit=2 表示有
规范章节未检测到：把缺失章节列入 result.json 的未检查项，禁止在报告中使用"全文"
"所有章节"字样。exit=3（空文本，如扫描件无文本层）：标 `未检查/no_text_layer`，
写明原因即交付诚实 partial，**不要硬审**。

### 第 2 步：生成主张候选

```bash
python3 $CL scaffold --work /app/work
```

得到 `claims_skeleton.json`：机械线索（表明/证明/导致/show/demonstrate/认为/reported/
有望…）扫出的主张候选，每条带 `attribution_hint`。hint 只是提示，允许推翻；清单之外
你判断实属主张的句子，自行补条（沿用同一 schema）。

### 第 3 步：逐条定案（主战场，判断全在这里）

对每条候选填：

- `attribution` 四选一。判据见 references/claim_taxonomy.md：句内带引用标记（[n]、
  (Name, year)、et al.）且谓词为转述动词 → `cited_view`；含假设标记（假设/假如/有望/
  hypothes/suppose）→ `hypothesis`；描述对照组、阴性对照等设计安排 → `control_or_design`；
  其余为 `author_claim`。
- `verdict` 四选一：`supported`（有文中证据且强度匹配）、`insufficient`（证据存在但
  撑不住表述强度）、`unsupported`（无证据或与证据相反）、`pending`（无法确认，note
  必须写清缺什么，如"被引文献原文不可得"）。
- `evidence_sentence_ids`：支撑或反驳该主张的句子 id（可多条，可跨章节——跨章节
  矛盾由此暴露）。
- 同时按 task.md 检查项覆盖六类审查：事实核验、引用支持、方法设计、统计报告、
  论证链、学术规范；清单 verdict 与证据栏是载体，不是全部。

### 第 4 步：过 lint 门禁

```bash
python3 $CL lint --work /app/work --claims /app/work/claims.json
```

exit=4 读 `ledger_lint.json` 逐条修正后重跑；**全部通过才能写入 /app/output**。门禁
强制：quote 逐字、归因/结论合法、author_claim 的 verdict 必须挂证据句、pending 必须
写原因、把转述/假设定为作者错误必须附说明。

### 第 5 步：交付

- `/app/output/result.json`：output_contract 全字段 + `case_id` + `status`（通过 / 问题 /
  待复核 / 未检查分列，不凭空补齐）+ findings（每条含 type ∈ {事实错误, 证据不足,
  规范问题, 建议, 待复核}、severity、sentence_id、quote、basis、suggestion）+
  `uncertainty` + `provenance`（引擎版本、清单条数、lint 通过时间）。
- `/app/output/report.md`：按严重度排序的人读报告；每条修改建议须可执行——说清
  补什么证据、改哪一句表述、把哪个结论的强度降到什么措辞。

## 严重度判据（详表见 references/claim_taxonomy.md）

- **critical**：影响主结论成立（unsupported 的作者核心主张、与结果相反的摘要结论）。
- **major**：削弱论证但主结论可救（关键主张 insufficient、跨章节口径冲突）。
- **minor**：局部问题（个别表述强度超标、次要主张缺引）。
- **info**：建议性意见。所有条目一律"中"是题目点名的失真，判据必须写明。

## 反误报规则（违反即质量问题）

1. 句内带 [n] / (Name, year) / et al. 且为转述动词 → 默认 cited_view，不得计作者缺陷。
2. 含假设标记或作者自注"有待验证" → hypothesis，最多建议补验证，不计错误。
3. 对照组、阴性/阳性对照、刻意基线 → control_or_design，不是自相矛盾。
4. 拿不准 → pending + note，**不凭空补结论**。

## 预算规划（64 次模型请求 / 900 秒）

工具调用不占模型预算。第 0–2 步 ≤6 次；第 3 步定案是主战场，按候选条数均分，
长清单优先 abstract/discussion 中的 author_claim；第 4–5 步 ≥4 次。预算吃紧时：
未定案条目一律 pending + note，诚实 partial 优于潦草全文。

## 异常处理

| 情况 | 处置 |
|-|-|
| 扫描版无文本层 | 标 `未检查/no_text_layer`，说明原因后交付 partial |
| 长文截断、缺章节 | 缺失部分列入未检查项；报告禁用"全文"字样 |
| lint exit=4 | 按 ledger_lint.json 逐条修正；禁止删 quote 绕过 |
| claimledger.py 报错 | 读 stderr，引擎总是显式报错；修输入不修引擎 |

## 不适用

文字润色、查重与学术不端判定、参考文献格式规范检查、原始数据重分析与统计复算、
投稿策略。本 Skill 不替代判断：它保证审的是真主张、引的是真原文、清单可逐条复核。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：手写合成短文，含作者主张、
Smith et al. 转述、作者自注假设、有意对照组四类句子。`sh examples/minimal/run_example.sh`
真实执行全管线：锚定 23 句 → 7 条主张候选 → 演示错误填法（伪造 quote + 把转述定为
作者错误）被 lint 拦下（exit=4，3 处违规）→ 合规填法通过。产物在
`examples/minimal/outputs/work/`，可目检。
