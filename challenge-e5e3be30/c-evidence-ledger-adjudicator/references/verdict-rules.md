# 公开裁决规则（verdict-rules.md）

> 本文件是四级判定的**唯一权威规则文本**，由 `scripts/verdict_engine.py` 逐条一致实现。
> 同一份台账输入永远得到同一个 verdict：可复现、可审计、可反驳。
> 对判定结果有异议时，**只能**补充/修正台账中的证据条目（并在 result.json 的
> `change_records` 中说明），**不允许**绕过本规则直接改写 verdict。

## 0. 记号定义

| 记号 | 定义 |
|---|---|
| `pro_same` | side=pro 且 polarity=same 的证据集合 |
| `con_opp` | side=con 且 polarity=opposite 的证据集合 |
| `PRO_D` | `pro_same` 中 strength=direct 的子集 |
| `CON_D` | `con_opp` 中 strength=direct 的子集 |
| 强度档 rank | direct=3 > indirect=2 > topical=1；集合为空记 0 |
| `pro_rank` / `con_rank` | `pro_same` / `con_opp` 的最高 rank |
| 锚点全集 `ALL` | 台账 anchors 中全部锚点 id |
| 核心锚点 `CORE` | type ∈ {number, comparator, negation} 的锚点 |
| `pro_covers` | `pro_same` 全部证据 covers 的并集 |
| `condir_covers` | `CON_D` 全部证据 covers 的并集 |
| `pro_full` | PRO_D ≠ ∅ 且 `ALL ⊆ pro_covers` |
| `con_core` | CON_D ≠ ∅ 且 `CORE ⊆ condir_covers` |
| `conflict` | ∃ e∈PRO_D, f∈CON_D：covers(e) ∩ covers(f) ≠ ∅ |

## 1. 四级语义（评测契约）

- **supported**：证据直接支持论断，全部锚点被 direct 证据覆盖。
- **partially_supported**：方向一致但只覆盖部分锚点，或只有 indirect 证据。
- **contradicted**：存在与论断极性相反的 direct 证据，且反驳强度 ≥ 支持强度。
- **insufficient_evidence**：只有 topical（主题相关）证据或无证据。
- 注意：**主题相关 ≠ 支持**；**未报告 ≠ 反驳**。

## 2. 决策树（自上而下，先命中先生效）

- **R1 无证据**：`evidence` 为空 → `insufficient_evidence`。
- **R2 完全支持**：`pro_full` 且 ¬`con_core` → `supported`。
- **R3 反驳**：`con_core` 且 ¬`pro_full` 且 `con_rank ≥ pro_rank` → `contradicted`。
  （反驳方 direct 覆盖全部核心锚点，且强度不低于支持方。）
- **R4 对撞基准**：`pro_full` 且 `con_core` → 基准判 `supported`，但此时
  PRO_D 与 CON_D 同时成立，通常经 R7 降级；若罕见地无锚点重叠（conflict=假），
  维持 `supported` 并在 reasons 中注明 CON_D 存在。
- **R5 部分支持**：存在 `pro_same` 且（`pro_rank ≥ 2` 或 PRO_D ≠ ∅ 但未全覆盖）
  → `partially_supported`。
- **R6 证据不足**：其余情形（只有 topical pro、或 pro 证据极性标注异常）
  → `insufficient_evidence`。**模型把主题相关判成 supported 时，由本条压回。**

## 3. 冲突降级

- **R7**：若 `conflict` 为真（正反双方 direct 证据在同一锚点上对撞），
  最终 verdict 在基准判定上**下调一档**：
  - supported → partially_supported
  - contradicted → partially_supported
  - partially_supported → insufficient_evidence
  - insufficient_evidence → insufficient_evidence（不再下调）
- 同时置 `conflict=true`，result.json 的冲突字段必须**并列双方 quote 原文与
  page/section 定位**（由 `scripts/conflict_pairs.py` 生成记录）。

## 4. 逐锚点核对表

裁决同时输出 `anchor_table`：每个锚点列出 `covered`（是/否）与
`covered_by`（证据 id 及 side/strength/polarity），供人工复核覆盖判定。

## 5. 典型情形速查

| 台账情形 | 规则链 | verdict |
|---|---|---|
| 空台账 | R1 | insufficient_evidence |
| 1 条 pro direct 覆盖全部锚点，无 con | R2 | supported |
| 摘要 pro direct（30%） vs 正文表 con direct（8%），锚点重叠 | R4→R7 | partially_supported + conflict |
| 论断"无影响"，正文报告显著升高（con direct 覆盖否定锚点），无 pro | R3 | contradicted |
| 只有引言/背景级 topical 证据 | R6 | insufficient_evidence |
| pro indirect 覆盖全部锚点 | R5 | partially_supported |
| pro direct 只覆盖部分锚点 | R5 | partially_supported |
