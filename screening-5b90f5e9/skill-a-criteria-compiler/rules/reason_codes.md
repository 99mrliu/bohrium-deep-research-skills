# 理由码注册表（criteriaforge-screen-engine）

每个判定（decisions.jsonl 每条记录、每条标准明细）必须带理由码。新增码必须先在本表注册再使用，禁止口头造码。

## 纳入类

| 码 | 含义 | 适用标准类型 | 证据要求 | 示例片段 |
|---|---|---|---|---|
| IN-ALL-MET | 全部纳入标准通过、无排除标准触发的记录级主理由码 | 记录级（非单标准） | 各纳入标准的 pass 证据齐备 | —（记录级合成码） |
| IN-POPULATION | 研究对象符合纳入标准 | inclusion | 题录中的人群描述原句 | "adults with type 2 diabetes" |
| IN-INTERVENTION | 干预/对照符合纳入标准 | inclusion | 干预与对照描述原句 | "randomized to empagliflozin or placebo" |
| IN-OUTCOME | 结局指标符合纳入标准 | inclusion | 结局指标描述原句 | "primary outcome was cardiovascular death" |

## 排除类

| 码 | 含义 | 适用标准类型 | 证据要求 | 示例片段 |
|---|---|---|---|---|
| EX-POPULATION | 研究对象不符（年龄、病种、物种等） | exclusion/inclusion fail | 显示不符人群的原句 | "adolescents aged 12 to 17 years" |
| EX-DESIGN | 研究设计不符（观察性、综述、病例报告等） | exclusion | 显示设计类型的原句 | "a retrospective cohort study" |
| EX-INTERVENTION | 干预或对照不符 | exclusion/inclusion fail | 干预描述原句 | "all patients received usual care" |
| EX-OUTCOME | 未报告要求的结局指标 | exclusion/inclusion fail | 实际结局描述原句 | "The primary endpoint was the change in HbA1c" |
| EX-LANGUAGE | 语言不符 eligible_languages | inclusion fail / 引擎边界 | 记录 language 字段或摘要语言 | （引擎可据 language 字段自动判定）**本方向强制 needs_human，不自动排除** |
| EX-NO-ABSTRACT | 摘要缺失或为空，无法判定 | 引擎边界 | field_status.abstract ≠ present | **本方向强制 needs_human，不自动排除** |
| EX-DUPLICATE | 精确重复副本（归一 DOI/题名精确相同） | 去重台账层 | dedup_ledger 的 match_key 与 member 列表 | 只用于 dedup_ledger.jsonl，不进 decisions |

## 边界类（一律 needs_human，不自动纳入也不自动排除）

| 码 | 含义 | 适用场景 | 证据要求 | 示例片段 |
|---|---|---|---|---|
| BND-PARTIAL-OVERLAP | 研究对象/干预仅部分重叠（如混合人群） | 判 uncertain 时由模型给出 | 显示混合/重叠的原句 + note | "adults with type 2 diabetes or prediabetes" |
| BND-ABSTRACT-ONLY | 仅凭摘要无法判定该标准，需全文确认 | 判 uncertain 时由模型给出 | note 说明缺失信息 | "全文才可能报告随机化方法细节" |
| BND-UNRESOLVED | 判定缺失或不确定未消解（含缺判定标准） | 引擎合成兜底 | 缺判定清单 | —（引擎合成码） |

## 使用规则

1. 记录级 `primary_reason_code`：excluded → 第一个失败标准的码；included → IN-ALL-MET；needs_human → 触发的 BND 码或 EX-LANGUAGE / EX-NO-ABSTRACT / BND-UNRESOLVED。
2. 单标准明细的 `reason_code` 取 criteria_table 中该标准注册的码；模型可在 judgment 里用 `reason_code` 覆盖（仅限已注册码），用于标记 BND-* 边界。
3. uncertain 判定必须写 `note` 说明不确定原因；pass/fail 且 evidence_required=true 必须给 `evidence_snippet`（题录原文片段）。
