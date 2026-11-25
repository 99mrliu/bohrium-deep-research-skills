# 遗漏说明（Omission Statement）

- case_id：syn-omission-demo-001
- 生成：omission_statement.py v1.0.0 @ 2026-11-25T09:02:54Z
- 性质：基于上游 judgments 的下游诊断；不构成对全局召回的声明；不含任何人工复核结论。

## 1. 排除了什么、按什么理由
排除总数：8。主理由码分布：
- `EX_POP_AGE`：3 条
- `EX_DESIGN_NOT_RCT`：2 条
- `EX_OUTCOME_NO_BMI`：2 条
- `EX_INT_NOT_GLP1`：1 条

## 2. 排除稳健性
- 单理由排除：4 条（占比 0.5）
- 无 not_met 依据的排除：1 条
- fragile_share=0.625（阈值 0.5），fragile_flag=True

## 3. 存在遗漏风险、须人工复核的条目（按风险分降序）
| rank | record_id | risk_score | 触发器 |
|---|---|---|---|
| 1 | R11 | 6 | excluded_without_not_met, uncertain_verdict |
| 2 | R05 | 5 | single_criterion_exclusion, uncertain_verdict |
| 3 | R06 | 5 | single_criterion_exclusion, weak_evidence_anchor |
| 4 | R03 | 3 | single_criterion_exclusion |
| 5 | R09 | 3 | single_criterion_exclusion |

## 4. 主题面覆盖报警
- facet `F3_comparator`（lifestyle intervention comparator）：纳入集在该主题面命中为 0。本快照无法区分“检索遗漏”“筛选过严”与“该面真空”；须人工回查检索式与排除理由后方可定性。

## 5. 本快照无法回答的问题
- 本诊断仅基于有限题录快照，无法回答数据库之外是否仍有未检出的合格文献（不声称全局召回）。
- facet 零纳入报警无法在本快照内定性为“检索遗漏”“筛选过严”或“该面真空”，须人工回查检索式与全文。
- 被排除记录中证据锚定弱的条目，其判定正确性须人工核对原文后才能确认。
- 本技能不重新执行初筛判定，上游 judgments 本身的系统性偏倚只能被标记、不能被本流程纠正。

## 6. 建议的后续人工动作
1. 按第 3 节工作清单顺序双人复核，先处理 excluded_without_not_met 与单理由排除。
2. 对每个 facet 零纳入报警，回查检索式是否覆盖该主题面、排除理由是否误伤。
3. 复核结论须由真实人工产生并单独留痕；本技能产物不构成复核结论。
