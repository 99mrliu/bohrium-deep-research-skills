# 比较矩阵（由 render_all.py 从 JSONL 记录确定性渲染）

> 唯一事实来源：work/cells.jsonl + work/decisions.jsonl。⟦C-xxx⟧ 为 cell_id，可回溯至记录的 (paper_document_id, paragraph_id)；⟦NR⟧ = not_reported。本文件由记录生成，请勿手工编辑。

## 1. 共同字段比较矩阵

| field | DOC-01 | DOC-02 | DOC-03 |
|---|---|---|---|
| catalyst_dosage_mg | 50 mg ⟦C-005⟧ | 40 mg ⟦C-011⟧ | — ⟦NR⟧ |
| degradation_efficiency_pct | 96 % ⟦C-003⟧ | 88 % ⟦C-009⟧ | — ⟦NR⟧ |
| material | g-C3N4 ⟦C-001⟧ | N-TiO2 ⟦C-007⟧ | g-C3N4-Ag ⟦C-013⟧ |
| pollutant | 罗丹明B (RhB) ⟦C-002⟧ | 亚甲基蓝 (MB) ⟦C-008⟧ | 罗丹明B (RhB) ⟦C-014⟧ |
| rate_constant_k | 0.035 min^-1 ⟦C-006⟧ | — ⟦NR⟧ | 0.031 min^-1 ⟦C-016⟧ |
| reaction_time_min | 90 min ⟦C-004⟧ | 120 min ⟦C-010⟧ | — ⟦NR⟧ |

## 2. 六维度可比性矩阵（C=comparable, N=not_comparable, NR=not_reported, U=unknown）

| document_id | field | task | metric | units | material | pollutant | budget |
|---|---|---|---|---|---|---|---|
| DOC-01 | catalyst_dosage_mg | C | C | C | C | C | C |
| DOC-01 | degradation_efficiency_pct | C | C | C | C | C | C |
| DOC-01 | material | C | C | C | C | C | C |
| DOC-01 | pollutant | C | C | C | C | C | C |
| DOC-01 | rate_constant_k | C | C | C | C | C | C |
| DOC-01 | reaction_time_min | C | C | C | C | C | C |
| DOC-02 | catalyst_dosage_mg | C | C | C | N | N | C |
| DOC-02 | degradation_efficiency_pct | C | C | C | N | N | C |
| DOC-02 | material | C | C | C | N | N | C |
| DOC-02 | pollutant | C | C | C | N | N | C |
| DOC-02 | rate_constant_k | NR | NR | NR | NR | NR | NR |
| DOC-02 | reaction_time_min | C | C | C | N | N | C |
| DOC-03 | catalyst_dosage_mg | NR | NR | NR | NR | NR | NR |
| DOC-03 | degradation_efficiency_pct | NR | NR | NR | NR | NR | NR |
| DOC-03 | material | C | C | C | C | C | NR |
| DOC-03 | pollutant | C | C | C | C | C | NR |
| DOC-03 | rate_constant_k | C | N | C | C | C | NR |
| DOC-03 | reaction_time_min | NR | NR | NR | NR | NR | NR |

## 3. 定量合成判定（任何数值合并之前必须过六维度检验；blocked 禁止合并）

- **D-001** [blocked] degradation_efficiency_pct 跨论文定量合成：DOC-02 污染物不同（亚甲基蓝 vs 罗丹明B，C-008）且材料体系不同（C-007），DOC-03 未报告效率（C-015）；依据规则不得合并不同染料或不同数据集，效率指标禁止跨文定量合并，仅并列呈现（依据：C-003, C-009, C-015）
- **D-002** [partial] rate_constant_k 跨论文比较：DOC-01 与 DOC-03 均报告 k 且均为 RhB/g-C3N4 基体系（C-006、C-016），可并列呈现；但禁止合并或平均不同数据集，且 DOC-02 未报告 k（C-012），DOC-03 的 k 无法换算为效率口径（依据：C-006, C-016, C-012）
- **D-003** [partial] budget（catalyst_dosage_mg）维度完整性：DOC-01/DOC-02 已报告投加量（C-005、C-011），DOC-03 未报告（C-018），budget 维度不完整，投加量归一化比较不可行（依据：C-005, C-011, C-018）
