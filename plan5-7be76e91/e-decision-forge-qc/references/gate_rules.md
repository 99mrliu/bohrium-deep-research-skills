# 质量门规则 ↔ 题目评分点映射（decision-forge-qc）

`scripts/quality_gate.py` 的每条机检规则对应题目「实验方案比较与选择」的一个评分
关注点。规则的权威实现是 `quality_gate.py` 源码；本表是语义说明。缺陷代码在
`gate_report.json` 的 `defects[].code` 中原样出现，便于机检对账。

## 规则一览

| 缺陷代码 | 规则语义 | 针对的题目失败模式 / 评分点 |
|---|---|---|
| `FIELD_GROUP_EMPTY` | 每个方案的七类字段（assumptions/variables/controls/steps/parameters/resources/evaluation_criteria）每组必须是非空数组 | 评分「完整性」：七类字段缺一不可；缺组即方案描述不完整 |
| `MATRIX_ENTRY_ID_MISSING` / `MATRIX_ENTRY_ID_DUPLICATE` | 矩阵每条目必须带全包唯一稳定 id | 可复核性：没有稳定 id 就无法做证据引用，结论无法对账 |
| `ELIMINATION_RULE_MISSING` | 每条 elimination 必须有非空 rule | 「结论强度靠语气不靠证据」：淘汰必须点名依据哪条规则，不允许「综合考虑后认为不合适」式淘汰 |
| `ELIMINATION_EVIDENCE_MISSING` | 每条 elimination 必须有非空 evidence_refs | 同上：淘汰必须挂证据，不允许空口淘汰 |
| `EVIDENCE_REF_UNKNOWN` | 每个证据引用必须指向包内存在的条目（矩阵条目 id / `<plan_id>.<category>` 组引用 / 确认项 id） | 「方案一换就说不清为什么改选」：引用悬空说明决策日志与材料脱节 |
| `ELIMINATION_PLAN_UNKNOWN` | elimination 必须指向 plans 中存在的方案 | 决策日志一致性 |
| `SELECTION_CITES_PENDING` | status=pending 的确认项 id 不得出现在 selection.rationale / discarded_reasons 文本中 | 「未经确认的建议不得写成可执行事实」：把待确认项写成已确认事实是题目点名的硬伤；脚本做保守词面检查（按 id 精确子串匹配），模型另有语义层面的自查义务 |
| `SELECTION_NOT_PROVISIONAL` | 存在 pending 确认项时 selection.status 必须为 `provisional` | 结论降级机制：确认项未完成 ⇒ 结论强度必须降级并在交付中写明 |
| `CONFIRMATION_KIND_UNKNOWN` / `CONFIRMATION_STATUS_UNKNOWN` | kind ∈ {safety, ethics, equipment_availability, expert}；status ∈ {confirmed, pending} | 确认项四类（安全/伦理/设备可用性/专家）是题目指定的完整性维度 |
| `SELECTION_PLAN_UNKNOWN` / `SELECTION_RATIONALE_MISSING` / `DISCARDED_REASONS_MISSING` / `SELECTION_STATUS_UNKNOWN` | selection 结构完整且指向存在的方案 | 交付结构完整性 |
| `SCORE_DIM_MISSING` / `WEIGHTS_INVALID` / `WEIGHTS_MISSING` / `SCORES_MISSING` | scores 覆盖 weights 全部维度且为数值；权重为正数 | 敏感性分析与排名可复算的前提；分数缺失 ⇒ 排名不可复核 |
| `SKELETON_CASE_ID_MISSING` / `SKELETON_CASE_ID_MISMATCH` / `CASE_ID_MISMATCH` | result_skeleton.case_id 必须存在且与决策包、case.json 一致 | 评测契约：result.json 必含正确 case_id |
| `CONTRACT_KEY_MISSING` | result_skeleton 必须含 case.json output_contract 的**全部原始键**（允许 status/sources/uncertainty 等额外键） | 评测契约「不漏键不臆造键名」；output_contract 键缺失是评测器直接可见的失分点 |
| `OUTPUT_CONTRACT_MISSING` | 提供 --case 时 case.json 必须含非空 output_contract | 对账前提 |
| `PLANS_MISSING` / `PLAN_ID_*` / `MATRIX_MISSING` / `ELIMINATIONS_MISSING` / `CONFIRMATIONS_MISSING` / `SELECTION_MISSING` / `RESULT_SKELETON_MISSING` / `PACKAGE_*` / `CASE_NOT_OBJECT` | 决策包顶层结构完整 | 决策包作为可独立复核交付物的基本形态 |

## 退出码语义

- `0`：0 个缺陷，决策包可进入敏感性分析与渲染；
- `2`：输入/用法错误（文件不存在、非 UTF-8、JSON 解析失败、无法写出报告）；
- `3`：≥1 个缺陷，stdout 打印逐条缺陷清单，`gate_report.json` / `gate_report.md`
  仍写出（能写的产物仍写出），决策包**不得**进入交付渲染，模型须先修复。

## 与其他脚本的分工

- `quality_gate.py` 管「能不能交付」；
- `sensitivity.py` 管「结论在权重扰动下稳不稳」（rank-flip 与翻转阈值）；
- `report_render.py` 管「交付形态是否自包含、可独立复核」（确认项分区、决策日志、页脚标注）。
三者都过，才允许模型把 `result_skeleton` 填成最终 `/app/output/result.json`。
