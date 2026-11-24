---
name: exp-source-reconciler
description: 写实验方案前对上游输入做保真与机械对账。当任务提供 case.json（含 resource_contract、parameter_domains、candidate_plans、可能内嵌补充设备的 equipment_domain_note，以及 /input 下可选论文 PDF）并要求产出或修订实验方案时使用：先用脚本把 case.json 提炼为带 JSONPath 定位的事实登记表（fact registry），再对候选方案做算术/参数域/合同覆盖/预算周期/依据定位五类对账，把 FAIL 作为修订靶点，最后基于登记表撰写每个数字都可溯源的完整方案。
---

# exp-source-reconciler — 上游输入保真与对账

## 1. 用途与新增价值

方案错误的一半源于输入理解错误：文本里内嵌的补充设备没解析、候选方案宣称的数字与合同不符、
单位/量纲混乱、领域标签与实际内容不符。本 skill 把"读懂输入"从肉眼活动变成机械活动：

- `scripts/case_reconcile.py extract` 把 case.json 摊平成 **事实登记表**（facts.json + facts.md），
  每条事实带 `id / value / unit / jsonpath / source_class`（合同/参数域/候选宣称/文献/文本内嵌补充/推断），
  并解析 `equipment_domain_note` 等文本字段里内嵌的 JSON/dict 片段，与 `equipment` 列表合并成
  **统一设备表**（标注 origin: contract / text_embedded）。
- `scripts/case_reconcile.py reconcile` 做五类机械对账（见 §4 与
  `references/reconciliation_rules.md`），输出 PASS/FAIL/WARN 与证据算式。
- `scripts/case_reconcile.py pdfscan` 在有论文 PDF 时用 pdftotext 提取文本并按 research_goal
  关键词定位摘录，**只报告真实页码**，工具不可用时如实报告。
- 修订方案的每个数字必须引用 fact id（规则见 `references/plan_citation_rules.md`），
  杜绝"方案里的数字无出处"。

## 2. 适用条件与不适用情况

**适用**：输入含 case.json（SPEC 结构：resource_contract / parameter_domains / candidate_plans /
output_contract，可能有 equipment_domain_note 与论文 PDF）；任务要求评估候选方案并产出修订方案。

**不适用**：无 case.json 的开放式问答；纯文献综述；候选方案与合同/参数域完全缺失且无对账对象
（此时直接按通用方案写作流程，不必强行套用本 skill）。

## 3. 运行时契约与路径

- 输入：`/input/case.json`、`/input/task.md`、可选 `/input/*.pdf`。
- 工作目录：`/app/work`（中间产物：facts.json、reconcile_report.json、pdf_excerpts.md）。
- 交付：`/app/output`，必含 `result.json`（字段见 §5）、`plan.json`、`plan.md`，
  并建议附 `facts.json`、`reconcile_report.json` 作为证据链。
- Skill 安装路径：`/skills/weekly-skill`，脚本为 `/skills/weekly-skill/scripts/case_reconcile.py`。
- 脚本仅用 Python 3 标准库，确定性，缺键不崩（exit 0 输出 partial 报告），单次 <5 秒。

## 4. 工作流

1. **读 case**：通读 `/input/task.md` 与 `/input/case.json`，记录 `output_contract.required_fields`。
2. **extract — 建事实登记表**：
   ```bash
   python3 /skills/weekly-skill/scripts/case_reconcile.py extract \
     --case /input/case.json --outdir /app/work
   ```
   检查输出中 equipment_table 的 `origin=text_embedded` 行——这些是文本内嵌补充设备，
   后续对账与方案都不得遗漏。
3. **reconcile — 机械对账**：
   ```bash
   python3 /skills/weekly-skill/scripts/case_reconcile.py reconcile \
     --case /input/case.json --facts /app/work/facts.json \
     --out /app/work/reconcile_report.json
   ```
   五类检查：(a) cost_items 行算术与 total_cost 合计（差额算式）；(b) 候选参数是否落在
   parameter_domains 的 range/enum/step 内；(c) 候选引用的设备/试剂是否在合同（含文本内嵌补充）内；
   (d) budget_cap/deadline_days/预约吞吐 vs total_cost/est_days；(e) 参数域 basis 标注的
   source 路径能否在 case 内定位。判据全集见 `references/reconciliation_rules.md`。
   **把每条 FAIL 登记为修订靶点**；WARN 进入 confirmation_items 候选。
4. **pdfscan（仅当 /input 下有 PDF）**：
   ```bash
   python3 /skills/weekly-skill/scripts/case_reconcile.py pdfscan \
     --inputdir /input --case /input/case.json --out /app/work/pdf_excerpts.md
   ```
   pdftotext 不可用或无 PDF 时脚本会如实写明；**不得捏造页码**，不得凭记忆引用文献数字。
5. **撰写修订方案**（覆盖六要素，缺一不可）：
   - 假设与变量：自变量/因变量/控制变量，每个取值引用 fact id 或标 ASSUME-n；
   - 对照组：基线（如文献 key_claim 对应条件）与对照设计；
   - 设备材料：只用统一设备表与合同试剂清单内的条目，文本内嵌来源需注明；
   - 时间成本：重算 cost_items 与 total_cost（修正对账发现的算术错），校核预算/周期/预约吞吐；
   - 参数范围：全部取值落在 parameter_domains 内；
   - 风险和异常：FAIL/WARN 项的处置、预约不确定性、前瞻合同性质。
   每个数字按 `references/plan_citation_rules.md` 标注 fact id（如 `[F023]`）；
   无法定位的数字标 `ASSUME-n` 并同步进 confirmation_items。
6. **自检**：grep 方案中全部数字，逐一确认有 fact id 或 ASSUME 标注；确认 FAIL 靶点均已处置；
   确认未把前瞻合同写成已确认报价。
7. **写 result.json**：按 §5 契约输出到 `/app/output`，附 status/uncertainty/change_log。

## 5. 输出契约

`/app/output/result.json` 必含 `case_id` 及 case.json `output_contract.required_fields`
列出的全部字段（SPEC 案例通常为：`case_id, revised_plan, candidate_assessment, validation,
status, uncertainty, sources, change_log, confirmation_items`）。其中：

- `status`: complete / partial / blocked（诚实标注）；
- `sources`: 使用的事实来源类别与关键 jsonpath；
- `uncertainty`: 前瞻合同性质、未确认假设、WARN 项；
- `change_log`: 相对候选方案的每处修订及对应的 reconcile check_id / fact id；
- `confirmation_items`: 所有 ASSUME-n、WARN 项、需组织方确认的前瞻约定。

`plan.json` 结构：`{case_id, fact_registry: "facts.json", revision_targets: [...], assumptions,
variables, controls, equipment_materials, schedule_cost, parameter_ranges, risks, citations}`；
`plan.md` 为人类可读版，六要素各一节，数字后随 `[Fxxx]` 引用。

## 6. 失败模式与止损表

| 失败模式 | 信号 | 止损 |
|---|---|---|
| case.json 损坏/缺键 | extract 输出 partial | 用 partial 报告中的已有事实继续，status=partial |
| 内嵌片段解析失败 | equipment_table 无 text_embedded 行但 note 文本可疑 | 人工复读 note 文本，把设备手工登记为 ASSUME-n |
| pdftotext 不可用 | pdfscan 如实报告 | 不引用任何文献页码，文献数字仅引 key_claim fact |
| 候选全部 FAIL 且不可修 | revision_targets 无法在给定域内消解 | status=partial，给出不可消解原因与所需输入 |
| 预算/周期硬冲突 | D 类 FAIL | 缩减实验矩阵规模并重算，仍冲突则进 confirmation_items |
| 模型预算不足 | 已用请求接近上限 | 立即按当前事实表写 partial result.json，再迭代完善 |

## 7. 输入缺失/约束冲突的降级（honest partial）

缺 source（无文献）→ 文献类事实缺席，方案中凡需文献支撑的数字一律 ASSUME-n；
缺 candidate_plans → 跳过候选评估，直接基于合同与参数域起草方案并注明无对账对象；
缺 parameter_domains → 参数范围改为"待确认"，全部进 confirmation_items；
约束冲突（预算<最低成本、周期<最短排期）→ 不硬凑方案，输出冲突算式 + 可选削减项，
status=partial。**任何降级都必须写进 uncertainty 与 change_log。**

## 8. 预算意识

64 次请求 / 900 秒预算下：机械工作全部交给脚本（extract/reconcile/pdfscan 共 3 次 bash，
<5 秒），模型只做三件事——读对账报告、写方案、自检。先写一版覆盖全部 required_fields 的
partial result.json 落盘，再用剩余预算迭代修订细节；不要先追求完美再落盘。
