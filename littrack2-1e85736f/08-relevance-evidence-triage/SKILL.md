---
name: relevance-evidence-triage
description: 对本地固化的多源文献快照（Crossref / Europe PMC / arXiv 等）做双阶段相关性分级筛选——确定性规则预筛加多维 rubric 透明打分——并为每条保留或排除的文献从题录原文装订逐字证据（verbatim quote + 字段 + 字符偏移），输出 PRISMA 式流转计数、排除原因分类、边界带 needs_human_review 标记与遗漏说明，最终按 output_contract 写 result.json；适用于"最新文献发现与追踪"中要求筛选决策可复核、可追溯、不编造证据的场景。
---

# relevance-evidence-triage：相关性分级筛选与依据装订

## 1. 适用场景与边界

**适用**：已有一批本地固化的文献题录快照（JSON），需要围绕一个研究问题筛选出相关文献，且要求：
- 每条保留/排除决策都可复核（打分逐分可解释、排除原因有分类）；
- 保留或待复核的文献必须装订**逐字**原文证据（从 title/abstract 切出的 quote + 所在字段 + 字符偏移）；
- 流转过程有 PRISMA 式计数（identified→prefiltered→screened→included），数量守恒；
- 拿不准的条目不强行二分，进入边界带 `needs_human_review`；
- 诚实交代遗漏面（未抽审的预筛排除类别、摘要缺失条目）。

**明确不做**（属于其他 skill 的范围，本 skill 不实现、不评价）：
- 去重键设计、增量水位/窗口调度、提醒合并抑制与投递、源完整性审计、增量台账、失败重试、版本链生命周期、检索式覆盖工程、QA 清单评分。
- 本 skill 中的"同标题重复→duplicate_of_kept"只是筛选决策的去向标注，不是去重管线。

## 2. 运行契约

- **输入**：`/input/case.json`（评测时）或任意路径的 case.json（本地）。字段约定见
  `examples/minimal/case.json`：`case_id`、`research_question`、`window`、
  `prefilter` 配置、`screening_rubric` 配置、`materials_dir`、`output_dir`、
  `output_contract.required_fields`。任务说明见同目录 `task.md`。
- **材料定位**：优先用 `case.json` 的 `materials_dir`；否则用 `common.find_materials_dir`
  的 find 兜底（case 同级 `materials/`，再向上两层及 `/input`、`/app/input`、`/app`
  下 walk 查找含 `.json` 的 materials/snapshots/data 目录）。找不到就如实在
  result.json 的 `limitations` 说明并 `status=partial`。
- **工作目录**：评测时用 `/app/work` 放中间产物；最终必须写
  `/app/output/result.json`（本地运行时写 `output_dir` 下的 `result.json`）。
- **result.json**：必须含 `case_id` 与 `output_contract.required_fields` 的**全部**
  字段；任何字段无法产出时**补 null 且 `status="partial"`**，绝不静默省略、绝不编造。
- **环境**：仅 Python3 标准库，完全离线；不得访问网络。

## 3. 编号工作流程

脚本做确定性部分；模型只做两件事：**在脚本切出的候选证据片段中选择最贴切者**、
**写一句话判断**（rationale_note）。模型绝不可自造"证据引文"。

1. **加载与归一化**（`scripts/common.py`）：定位材料目录，把 Crossref
   （message.items）/ Europe PMC（resultList.result）/ arXiv（entries）三种布局
   归一化为统一题录；无法识别的快照跳过并记录。
2. **预筛**（`scripts/prefilter.py`）：确定性规则——语言白名单、文献类型排除、
   窗口内日期、标题明显无关词表；命中即排除并记 `category`。语言或日期缺失时
   **放行但打标**（`language_unknown` / `date_unknown`），进入遗漏说明。产物
   `prefilter_results.jsonl`。
3. **rubric 打分与决策**（`scripts/rubric_score.py`）：按 `screening_rubric` 逐维度
   命中词表加/减分，逐条写 `score_entries`（维度、命中词、分值、字段）。决策：
   `|score-threshold| <= delta` → `needs_human_review`；高于带 → `included`；
   低于带 → `excluded`（类别由被触发的负向维度映射，兜底 `off_topic_low_score`）。
   规范化标题相同的条目标 `duplicate_of_kept`。摘要缺失 → `title_only=true`。
   产物 `screening_decisions.jsonl`。
4. **证据装订**（`scripts/evidence_bind.py`）：对 included / needs_human_review
   条目，按正向命中的维度从 title/abstract 原文切句，产出候选片段
   （quote + field + char_start/char_end + dimension），写 `evidence_candidates.json`。
   **模型随后阅读 candidates，为每条记录选择最贴切的 1~3 段**写入
   `evidence_selected.json`（并可在 decisions 中补 `rationale_note`）。quote 只能选、
   不能改一个字符。
5. **流转计数**（`scripts/prisma_flow.py`）：生成 `prisma_flow.json`，含每层数量、
   按类别的去向、两条守恒不变量；不守恒即报错。
6. **组装**（`scripts/assemble_result.py`）：汇总 included（带证据）/
   needs_human_review（带边界带说明）/ excluded（带类别）、遗漏说明、limitations，
   按 `output_contract.required_fields` 强制校验后写 `result.json`。
7. **自查**：按第 6 节清单逐项核验；`scripts/run_minimal_example.py` 给出可复制的
   端到端参照实现与自检代码。

## 4. 异常处理（诚实降级）

| 异常 | 处理 |
|---|---|
| 摘要缺失 | 只按标题打分，`title_only=true`，单独列入 `omission_notes.title_only_records`，并在 limitations 说明置信度低 |
| 语言/日期字段缺失 | 预筛放行但打标，列入遗漏说明；不误杀也不假装知道 |
| rubric 不适用于某条（无任何命中） | 得分 0 → excluded / `off_topic_low_score`，如实记录"无命中词" |
| 快照布局无法识别 | 跳过该文件并在 limitations 列出文件名 |
| 证据候选为空（included 但切不出片段） | 该条 evidence 为空数组，`status=partial` 并说明 |
| PRISMA 计数不守恒 | 立即报错，不写"看起来正常"的 result |
| 必填字段无法产出 | 补 null，`status=partial`，limitations 逐条列出 |

## 5. 输出契约

`result.json` 字段（以 case.json 的 `output_contract.required_fields` 为准）：
- `case_id`、`status`（"ok" | "partial"）、`research_question`、`screening_window`；
- `prisma_flow`：identified / prefiltered_out（含 by_category）/ screened /
  included / needs_human_review / excluded_at_screening（含 by_category）/
  invariants / ok；
- `included[]`：record_id、score、score_entries、**evidence[]**（quote/field/
  char_start/char_end/dimension/matched_term）、title_only、rationale_note；
- `needs_human_review[]`：同上 + `band`（threshold/delta/说明）；
- `excluded[]`：record_id、stage（prefilter|screening）、category、category_evidence；
- `exclusions_by_category`、`evidence_policy`、`omission_notes`、`limitations`、`artifacts`。

## 6. 自查清单（交付前逐项核验）

1. **证据逐字性**：对 result.json 中每条 evidence，重新加载对应快照，核验
   `text[field][char_start:char_end] == quote`（可调用
   `evidence_bind.verify_binding`）；随机抽查 ≥5 条候选片段同样核验。有任何一条
   对不上 = 失败，必须返工。
2. **偏移可复算**：char_start/char_end 是对快照中存储的字段文本的偏移；若快照含
   标记（如 JATS），必须在 `evidence_policy.normalization` 说明归一化方式。
3. **无编造**：included/excluded 中的 record_id、标题、DOI 全部来自快照，未出现
   快照之外的文献或"听起来合理"的元数据。
4. **PRISMA 守恒**：两条不变量均为 true。
5. **边界带**：阈值±δ 内的条目全部 `needs_human_review`，未被强行二分。
6. **遗漏说明**：预筛排除类别、title_only 条目均已列出。
7. **契约完整**：required_fields 全部存在；缺失项为 null 且 status=partial。
8. **合成标注**：示例/合成数据必须带 `synthetic` 与 `synthetic_note`，不得冒称真实。

## 7. 文件索引

- `scripts/`：common.py、prefilter.py、rubric_score.py、evidence_bind.py、
  prisma_flow.py、assemble_result.py、run_minimal_example.py
- `references/`：rubric_spec.md（打分表与阈值）、exclusion_taxonomy.md
  （排除原因分类法）、prisma_and_borderline.md（PRISMA 流转与边界带规则）
- `examples/minimal/`：合成端到端示例（case.json、task.md、materials/、output/）
