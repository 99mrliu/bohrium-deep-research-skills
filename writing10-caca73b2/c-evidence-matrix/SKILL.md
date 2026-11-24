---
name: discussion-evidence-matrix
description: 面向论文结果与讨论章节写作的论断×来源证据矩阵技能。该技能要求讨论部分的每条论断先进入结构化论断台账（claims.json），并以类型化锚点标注出处——自数据锚点 [Dnn] 指向材料中的图/表/统计输出，文献锚点 [Lnn] 指向材料提供的参考文献表，且每个文献锚点必须显式声明与论断的关系（一致/不一致/部分一致/机制解释/背景）。配套的三个确定性脚本（result_contract.py、build_matrix.py、cite_check.py）在交付前执行双审计：无锚论断不得进入正文、文献引用必须真实存在于给定文献表、一致/不一致关系必须在句中措辞化、未使用文献如实报告而非强行堆砌，从流程上解决"只堆引用不讲关系、论断无出处、引用材料中不存在的文献"三类顽疾。Use when writing or auditing the Discussion section of a results-and-discussion chapter so that every claim is traceable to a figure/table/statistic or to a provided reference, every citation actually exists in the supplied materials, and agreement or disagreement with the literature is stated explicitly.
---

# 讨论证据对照：论断×来源证据矩阵 + 引用存在性核验

## 解决的问题

讨论章节的常见失败不是写得不够多，而是论断与证据脱钩：

1. **只堆引用不讲关系**：段落末尾缀一排文献，却不说明本研究与它们一致、
   不一致还是部分一致，更不给可能原因；
2. **论断无出处**：数值、比较级结论（"最优""显著提升"）悬空出现，
   无法回溯到具体图、表或统计输出；
3. **引用材料中不存在的文献**：凭印象生成"看起来很真"的参考文献，
   评审无法在给定材料中核到，属于幻觉引用。

本技能的对应手段：论断台账（claims.json）强制每条论断登记锚点；
双审计脚本（build_matrix.py、cite_check.py）以确定性规则核验
"无孤儿论断、无装饰引用、引用必存在、关系必措辞化"，FAIL 必须修复，
不得绕过。

## 何时使用

- 撰写或改写论文结果与讨论章节的讨论部分，且输入材料中包含本研究结果
  （图、表、统计输出）和参考文献表；
- 审查已有讨论稿：检查论断是否都有出处、引用是否真实存在、
  与文献的关系是否明说。

## 何时不适用

- 材料中没有可供挂锚的结果（无图无表无统计输出）——此时讨论无从锚定，
  应先在 uncertainty 中说明，不得编造锚点；
- 纯文献综述、引言写作（无本研究数据）——锚点体系以 Dnn 为核心，
  不适用；
- 需要全文语言润色、结构调整的任务——本技能只管证据对照与引用核验。

## 运行契约

- **输入**（只读）：`/input/case.json`（含 `case_id` 与 `output_contract`）、
  `/input/task.md`、以及真实研究材料（PDF、表格、给定参考文献列表等，
  以实际挂载为准）。
- **工作区**：`/app/work`——台账、登记表、讨论草稿、审计中间产物均放此处。
- **交付**：`/app/output`——讨论正文、证据矩阵、审计报告，以及
  **`result.json`**。`result.json` 必须包含：
  - `case_id`：与 case.json **原样一致**，不改写、不补全；
  - `output_contract` 声明的**全部键**（标准键为 `deliverable`、
    `preserved_facts`、`evidence_map`、`change_log`，以 case.json 实际为准），
    每个键非空，或在 `_notes` 中说明暂缺原因；
  - `status`（`partial`/`complete`/`failed`）、`sources`、`uncertainty`，
    三者必须诚实填写。
- **诚实 partial**：预算或材料不足时，尽早保存部分结果，
  `status="partial"`，未完成键在 `_notes` 说明原因。诚实 partial 优于
  编造完整。

## 依赖

Python >= 3.9，仅标准库（argparse / json / re / sys）。三个脚本均支持
`--help`，退出码：0 = PASS/成功，1 = FAIL/存在 ERROR。

## 工作流（按序执行）

**步骤 0｜读任务、抄契约。** 读 `/input/task.md` 与 `/input/case.json`，
原样抄录 `case_id` 与 `output_contract` 全部键名。

**步骤 1｜初始化 result.json 骨架。**
`python3 scripts/result_contract.py init --case /input/case.json --out /app/output/result.json`
此后每完成一个阶段就回填一次，保证任何时候都有可交付的诚实 partial。

**步骤 2｜盘点材料、登记锚点。** 在 `/app/work/anchors.json` 中建立两份清单：
- 自数据锚点清单 D：逐个登记材料中的图、表、统计输出（D01、D02……），
  每项记录类型、出处、关键数值事实；
- 文献锚点清单 L：逐条登记**材料实际提供的**参考文献（L01、L02……）。
  查不到对应文献的标 `gap` 并在 uncertainty 中说明，**不得编造**。

**步骤 3｜建论断台账 claims.json。** 每条论断登记：
`id`（Cnn）、`text`（论断正文）、`anchors`（锚点列表，文献锚点须带
`relation`：一致/不一致/部分一致/机制解释/背景；自数据锚点为「支持」）、
`strength`（直陈/初步/推测）。字段细节见 `references/claims-schema.md`，
论断类型与语气模板见 `references/discussion-evidence.md`。

**步骤 4｜按台账写讨论。** 逐条论断成段，句内挂锚（`[Dnn]`/`[Lnn]` 写在
论断所在句内）；与文献一致/不一致之处必须明说关系，不一致须给可能原因；
数值一字不改地取自材料。

**步骤 5｜双审计，FAIL 必须修复。**
```
python3 scripts/build_matrix.py --claims claims.json --anchors anchors.json \
    --discussion discussion.md --out evidence_matrix.md --json coverage.json
python3 scripts/cite_check.py --discussion discussion.md \
    --bib <材料提供的文献表> --out cite_report.md
```
任一脚本退出码为 1 即回到步骤 3 或 4 修复，**不得绕过或删除报错论断以
充数**——删除须记入 change_log 并说明理由。

**步骤 6｜组装 result.json 并终检。** 填齐契约键后：
`python3 scripts/result_contract.py check --case /input/case.json --result /app/output/result.json`
PASS 方可交付。

## 红线

1. 只引用材料中实际存在（或实际检索到并记入 sources）的文献；
   任何 [Lnn] 必须能在给定文献表中核到；
2. 无锚论断不进正文；正文出现的每个 [Lnn] 必须挂在某条论断上，
   不做装饰引用；
3. 与文献不一致之处必须如实写"不一致"并给可能原因，
   不得为求叙事顺滑而回避；
4. 语气强度（直陈/初步/推测）由 relation 与证据数量决定：
   单一来源的机制解释不得写成"直陈"；
5. 数值不得四舍五入、改写或"优化"，必须与材料一致。

## 异常处理

| 异常 | 处理 |
|---|---|
| 材料无参考文献表 | L 清单为空；正文不得出现任何 [Lnn]；在 uncertainty 说明"无法做文献对照"；cite_check.py 会以 ERROR 拦截任何引用 |
| 文献信息不全（缺年/缺题名） | 照常登记；cite_check.py 报 WARN；在 uncertainty 中列出可疑条目 |
| 锚点歧义（一条材料可对应多个锚点） | 取最具体者（统计数字挂统计输出锚点而非整张表），并在 anchors.json 的 key_fact 中写清锚定的是哪个数值 |
| 论断台账与正文对不上（改写后失配） | 以 build_matrix.py 的"论断正文未出现"错误为准，优先改正文使其与台账一致，或同步更新台账并记入 change_log |

## 限制

- 锚点定位基于句号等句读切句与空白归一化匹配，论断改写后须同步台账；
- 关系措辞核验是关键词级检查（一致/不一致/部分一致及同义词），
  不能理解语义，措辞过于迂回时可能误报，此时应改用明说的措辞而非绕过；
- 文献表解析支持行式（`Lnn | 作者. 题名. 刊名, 年.`）与 BibTeX 两种格式；
- 脚本不核验数值本身是否与图/表一致（数值保真由 preserved_facts 与
  人工/模型核对负责），只核验锚点存在性与引用真实性。
