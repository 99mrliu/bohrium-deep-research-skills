---
name: exp-risk-fmea
description: 当任务要求把实验/研究方案做成"可执行"时使用——尤其是 case.json 给出候选方案、资源合同与有限参数域，需要为每个步骤绑定失效模式、可观测判据、止损点与替代路径，按 严重度×发生度×可探测度(RPN) 排优先级并反向修改设计（预防优于处置），最终交付覆盖六要素（假设与变量、对照组、设备材料、时间成本、参数范围、风险和异常）的完整方案。基础 Agent 只写"注意安全"时，用本 skill 把风险章节机械化生成并审计到 100% 覆盖。
---

# exp-risk-fmea：失效模式驱动设计

## 1. 用途与新增价值

基础 Agent 写风险只有一句"注意安全"。本 skill 把风险工程机械化：

- **map**：按步骤原型关键词把方案步骤表映射到失效模式库，每条失效模式带
  可观测判据 / 判据确认方法 / 止损点 / 替代路径 / 责任人 / 升级条件 / S·O·D 评分与 RPN；
  未覆盖步骤打 `ORPHAN-WARN`。
- **audit**：机械审查风险完备性（步骤覆盖率、失效模式四要素齐全率、
  confirmation_items 四类覆盖率），输出缺口清单。
- **decision_tree**：高 RPN（或 severity=5）失效模式生成 anomaly_tree.md：
  异常发生 → 判据确认 → 止损动作 → 替代路径 → 何时升级人工/专家确认。
- **render**：把 risk_map.json 机械渲染成方案"风险与异常处置"章节，**禁止手写一句带过**。
- 高优先级失效模式必须**反向修改设计**（design_feedback：预实验、双供应商、替代设备、
  校准确认点），预防优于处置。

## 2. 适用条件与不适用情况

适用：多步骤实验/研究方案的风险设计、候选方案风险审查、异常处置预案、
交付前完备性审计（任何学科：材料合成、生物培养、测量表征等，词表可扩展）。

不适用：纯理论/纯计算无实验步骤的任务（失效模式库无对应原型，此时诚实说明并降级为
通用 checklist）；库内失效模式模板不得替代机构安全规章（MSDS、应急预案以本单位为准）。

## 3. 运行时契约与路径

- 输入：`/input/case.json`（+ 可能的 `/input/task.md`、论文 PDF）。
- 工作目录：`/app/work`；交付：`/app/output`。
- 本 skill 安装于 `/skills/weekly-skill`，脚本路径 `/skills/weekly-skill/scripts/risk_fmea.py`，
  失效模式库 `/skills/weekly-skill/references/failure_mode_library.md`。
- `result.json` 必须含 `case_id` 与 case.json `output_contract.required_fields` 全部字段，
  诚实标注 `status`（complete/partial/blocked）、`sources`、`uncertainty`、`change_log`。

## 4. 工作流（编号步骤，命令可直接复制）

1. **读 case**：解析 `/input/case.json` 的 resource_contract（前瞻合同，非已确认报价）、
   parameter_domains（硬约束）、equipment_domain_note（文本内嵌设备，需解析对账）、
   candidate_plans（可能有算术错误/越域参数/超排期 est_days——靠脚本与对账发现，不凭肉眼）。
2. **初拟步骤表** `/app/work/plan_steps.json`：`{"steps":[{"id":"ST-01","name":"...",
   "description":"...","tags":["..."],"overrides":{"FM-XXX":{"occurrence":4,"reason":"证据定位"}}}]}`，
   6–10 步；名称/tags 尽量命中库关键词，命不中加 `prototype_hint`；评分调整必须写
   `reason` 并定位到 case.json 路径或标注为假设。
3. **map**：
   `python3 /skills/weekly-skill/scripts/risk_fmea.py map --case /input/case.json --steps /app/work/plan_steps.json --out /app/work/risk_map.json`
   出现 `ORPHAN-WARN` → 回第 2 步补关键词或 prototype_hint。
4. **高 RPN 反向改设计**：对 risk_map 中 `high_priority=true` 的条目，逐条把
   `design_feedback` 落成方案实体改动（如关键步骤加预实验、关键试剂双供应商策略写入
   confirmation_items、排期紧张设备写替代设备策略、温控步骤前置校准确认点）。
5. **写 confirmation_items** `/app/work/confirmation_items.json`：按
   `references/confirmation_checklist.md` 覆盖安全/伦理/设备可用性/专家确认四类；
   前瞻合同的排期与价格只能写成待确认项。
6. **audit 迭代（≤3 轮）**：
   `python3 /skills/weekly-skill/scripts/risk_fmea.py audit --risk-map /app/work/risk_map.json --confirmations /app/work/confirmation_items.json --out /app/work/audit_report.json`
   verdict=GAP 就按 gaps 修复后重跑 map+audit；3 轮仍不达标 → result.json 标 partial 并写明缺口。
7. **decision_tree**：
   `python3 /skills/weekly-skill/scripts/risk_fmea.py decision_tree --risk-map /app/work/risk_map.json --out /app/output/anomaly_tree.md`
8. **render 风险章节**：
   `python3 /skills/weekly-skill/scripts/risk_fmea.py render --risk-map /app/work/risk_map.json --out /app/work/risk_section.md`
9. **完成完整方案** `/app/output/plan.json` + `/app/output/plan.md`：必须覆盖六要素——
   假设与变量（含来源定位）、对照组（空白/标准样/重复次数）、设备材料（含
   equipment_domain_note 内嵌设备对账、前瞻合同免责声明）、时间成本（预算与排期算术）、
   参数范围（限 parameter_domains，越域须专家确认）、风险和异常（**粘贴 render 生成的
   risk_section.md 全文** + anomaly_tree.md，禁止手写概括）。
10. **result.json** 落盘 `/app/output/result.json`（结构见下节）。

## 5. 输出契约

`/app/output/`：

- `plan.json`：`{"case_id", "assumptions_and_variables", "controls", "equipment_materials",
  "schedule_budget", "parameter_ranges", "steps"(含每步 risk 引用 risk_map 条目 id),
  "risk_section_source":"risk_map.json 机械生成", "confirmation_items"}`。
- `plan.md`：六要素章节齐全；"风险与异常处置"章节 = risk_section.md 原文。
- `anomaly_tree.md`：decision_tree 输出。
- `result.json`：`{"case_id", "revised_plan"(摘要+关键改动), "candidate_assessment"
  (候选方案算术/参数域/排期对账结论), "validation"(audit verdict、覆盖率、脚本清单),
  "status", "uncertainty", "sources", "change_log", "confirmation_items"}`——
  字段以 case.json `output_contract.required_fields` 为准逐项核对。

## 6. 失败模式与止损表

| 失败模式 | 判据 | 止损 | 替代路径 |
|---|---|---|---|
| 库文件缺失/JSON 坏 | map 输出 `status:partial` + error | 停止依赖映射的后续步骤 | 检查 `--library` 路径；按 references 字段约定修复 JSON 后重跑 |
| ORPHAN 步骤 | risk_map `flags:["ORPHAN-WARN"]` | 不进入 audit | 给步骤补 tags/`prototype_hint`，或扩展库 prototypes 关键词 |
| audit 3 轮仍 GAP | audit_report `verdict:GAP` | 不伪造覆盖率 | result.json 标 partial，gaps 原文写入 uncertainty |
| severity=5 被漏判 | decision_tree 无 FM-SAFETY | 检查步骤是否匹配到含 FM-SAFETY 的原型 | 涉危化/高温步骤强制 `prototype_hint` |
| 评分拍脑袋 | override 无 `reason` | 退回该评分 | 默认值来自库；任何调整须定位到 case.json 路径或标注假设 |

## 7. 输入缺失/约束冲突的降级（honest partial）

- case.json 缺 `parameter_domains`：方案参数全部标"假设"，confirmation_items 加专家确认条目。
- 缺 `resource_contract`：时间成本章节只给相对工作量，预算标 unknown，status=partial。
- 脚本任何子命令输出 `status:partial`：带上 error 字段继续能做的工作，最终
  result.json 汇总各 partial 来源；**绝不**为凑 complete 而编造数据。
- 预算 cap 与必要成本冲突 / deadline 与排期吞吐冲突：写明冲突算术，提交人工决策，
  status=partial。

## 8. 预算意识（先存 partial 再迭代）

- 机械工作全部交脚本（map/audit/decision_tree/render 单次 <5 秒，零模型请求）。
- 模型预算优先给：读 case、初拟步骤表、高 RPN 设计修改、result.json 汇总。
- 每完成一个里程碑立即落盘（plan_steps → risk_map → audit_report → plan → result），
  任何时刻被打断都有可交付的 partial。
- audit 最多 3 轮；不要为完美措辞反复重写 plan.md，风险章节一律用 render 产物。
